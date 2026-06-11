"""Topic clustering beyond tickers: embed → reduce to 2-D → density cluster
→ c-TF-IDF labels.

Backends (EMBED_BACKEND, default `auto`):
- sentence-transformers (all-MiniLM-L6-v2) + UMAP — the full stack, used in
  the GitHub Actions worker where requirements-ml.txt is installed.
- TF-IDF + TruncatedSVD + t-SNE — pure scikit-learn fallback that runs
  anywhere with zero heavy deps (demo mode). Same downstream clustering.

Clustering is HDBSCAN (scikit-learn's built-in implementation), labels via
class-based TF-IDF over each cluster's vocabulary.
"""

from __future__ import annotations

import re
from collections import Counter

import numpy as np

from worker.config import settings
from worker.models import Post

MAX_POSTS = 3000  # embedding budget per run
STOPWORDS = set("""
a about after all also an and any are as at be been before being but by can
could did do does for from had has have he her his how i if in into is it its
just like me more most my no not now of on one or our out over so some than
that the their them then there these they this to up us was we were what when
which who will with would you your yours im its dont thats whats theres
""".split())


def _clean_for_vocab(text: str) -> str:
    text = re.sub(r"\$[A-Za-z.]{1,6}", " ", text)      # strip cashtags
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-zA-Z\s-]", " ", text).lower()
    return " ".join(w for w in text.split() if w not in STOPWORDS and len(w) > 2)


def _st_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        return False


def embed_and_project(texts: list[str], backend: str) -> np.ndarray:
    """Return (n, 2) coordinates for the landscape map."""
    if backend == "sentence-transformers":
        from sentence_transformers import SentenceTransformer
        import umap

        model = SentenceTransformer("all-MiniLM-L6-v2")
        emb = model.encode(texts, batch_size=64, show_progress_bar=False)
        reducer = umap.UMAP(n_components=2, n_neighbors=15, min_dist=0.08,
                            metric="cosine", random_state=42)
        return reducer.fit_transform(emb)

    # scikit-learn fallback: TF-IDF → SVD(50) → t-SNE(2)
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import TruncatedSVD
    from sklearn.manifold import TSNE

    vec = TfidfVectorizer(max_features=4000, ngram_range=(1, 2), min_df=2)
    X = vec.fit_transform([_clean_for_vocab(t) or "empty" for t in texts])
    n_comp = min(50, X.shape[1] - 1, X.shape[0] - 1)
    Xr = TruncatedSVD(n_components=max(2, n_comp), random_state=42).fit_transform(X)
    perplexity = min(40, max(5, len(texts) // 60))
    return TSNE(n_components=2, perplexity=perplexity, random_state=42,
                init="pca", max_iter=600).fit_transform(Xr)


def cluster_points(coords: np.ndarray) -> np.ndarray:
    from sklearn.cluster import HDBSCAN

    min_cluster = max(28, len(coords) // 55)
    labels = HDBSCAN(min_cluster_size=min_cluster, min_samples=5).fit_predict(coords)
    return labels


def _terms(doc: str) -> Counter:
    """Unigrams + bigrams — bigrams ('rate cut', 'short interest') usually
    make far better topic labels than single words."""
    tokens = doc.split()
    counts = Counter(tokens)
    counts.update(f"{a} {b}" for a, b in zip(tokens, tokens[1:]))
    return counts


def ctfidf_labels(texts: list[str], labels: np.ndarray, top_n: int = 6) -> dict[int, list[str]]:
    """Class-based TF-IDF: concatenate each cluster's docs, weight terms by
    in-cluster frequency × inverse cross-cluster frequency."""
    clusters = sorted(set(labels) - {-1})
    docs_per_cluster = {
        c: " ".join(_clean_for_vocab(t) for t, l in zip(texts, labels) if l == c)
        for c in clusters
    }
    tf: dict[int, Counter] = {c: _terms(doc) for c, doc in docs_per_cluster.items()}
    df = Counter()
    for counts in tf.values():
        df.update(counts.keys())
    n_clusters = max(1, len(clusters))
    out: dict[int, list[str]] = {}
    for c, counts in tf.items():
        total = sum(counts.values()) or 1
        scores = {
            # 1.6× boost steers labels toward bigrams when they're competitive
            term: (cnt / total) * np.log(1 + n_clusters / df[term]) * (1.6 if " " in term else 1.0)
            for term, cnt in counts.items() if cnt >= 2
        }
        picked: list[str] = []
        for term, _ in sorted(scores.items(), key=lambda kv: -kv[1]):
            # skip unigrams already covered by a chosen bigram and vice versa
            if any(term in p or p in term for p in picked):
                continue
            picked.append(term)
            if len(picked) == top_n:
                break
        out[c] = picked
    return out


def compute_topics(posts: list[Post], backend: str | None = None) -> dict:
    """Returns {"topics": [...], "points": [...]} and writes topic_id back
    onto the posts that were clustered."""
    backend = backend or settings.embed_backend
    if backend == "auto":
        backend = "sentence-transformers" if _st_available() else "tfidf"

    sample = posts[-MAX_POSTS:] if len(posts) > MAX_POSTS else list(posts)
    if len(sample) < 50:
        return {"topics": [], "points": [], "backend": backend}
    texts = [p.text for p in sample]

    coords = embed_and_project(texts, backend)
    labels = cluster_points(coords)
    term_labels = ctfidf_labels(texts, labels)

    topics = []
    for c in sorted(set(labels) - {-1}):
        members = [p for p, l in zip(sample, labels) if l == c]
        scored = [p.sentiment_score for p in members if p.sentiment_score is not None]
        tickers = Counter(t for p in members for t in p.tickers)
        terms = term_labels.get(c, [])
        label = " / ".join(terms[:3]) if terms else f"topic {c}"
        topics.append({
            "id": int(c),
            "label": label,
            "terms": terms,
            "size": len(members),
            "sentiment_avg": round(sum(scored) / len(scored), 4) if scored else 0.0,
            "tickers": [{"ticker": t, "count": n} for t, n in tickers.most_common(6)],
        })

    # Normalize coords to [0,1] for resolution-independent rendering.
    mins, maxs = coords.min(axis=0), coords.max(axis=0)
    span = np.where((maxs - mins) > 0, maxs - mins, 1)
    norm = (coords - mins) / span

    points = []
    for p, (x, y), label in zip(sample, norm, labels):
        p.topic_id = int(label) if label != -1 else None
        points.append({
            "post_id": p.id,
            "topic_id": int(label),
            "x": round(float(x), 4),
            "y": round(float(y), 4),
            "text": p.text[:200],
            "platform": p.platform,
            "sentiment": p.sentiment,
            "engagement": p.engagement,
            "tickers": p.tickers[:4],
        })
    return {"topics": topics, "points": points, "backend": backend}
