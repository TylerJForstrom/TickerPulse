import { json, serveMeta } from "./_shared/store.mjs";

export default async (req) => {
  const symbol = new URL(req.url).searchParams.get("symbol");
  if (!symbol || !/^[A-Z.]{1,6}$/.test(symbol)) {
    return json({ error: "symbol query param required, e.g. ?symbol=NVDA" }, 400);
  }
  return serveMeta(`ticker:${symbol}`);
};
