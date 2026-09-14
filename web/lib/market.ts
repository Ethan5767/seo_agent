/**
 * Which Google market a project's search data is measured in.
 *
 * DataForSEO measured every project against Google United States (2840) because
 * no market was sent; a Cambodian hospital (.kh) got US keyword volumes and US
 * rankings (2026-09-14). A single global setting would be wrong the other way
 * for a generic-domain project in the same account.
 *
 * Rule, stated rather than guessed: a country-code domain sets the country; any
 * other domain is United States. Codes are Google Ads geo target ids, which
 * DataForSEO uses as `location_code`.
 */

export type Market = { location_code: number; language_code: string; country: string };

const BY_CCTLD: Record<string, Market> = {
  kh: { location_code: 2116, language_code: "en", country: "Cambodia" },
  th: { location_code: 2764, language_code: "en", country: "Thailand" },
  vn: { location_code: 2704, language_code: "en", country: "Vietnam" },
  sg: { location_code: 2702, language_code: "en", country: "Singapore" },
  my: { location_code: 2458, language_code: "en", country: "Malaysia" },
  id: { location_code: 2360, language_code: "en", country: "Indonesia" },
  ph: { location_code: 2608, language_code: "en", country: "Philippines" },
  au: { location_code: 2036, language_code: "en", country: "Australia" },
  nz: { location_code: 2554, language_code: "en", country: "New Zealand" },
  uk: { location_code: 2826, language_code: "en", country: "United Kingdom" },
  ca: { location_code: 2124, language_code: "en", country: "Canada" },
  in: { location_code: 2356, language_code: "en", country: "India" },
  us: { location_code: 2840, language_code: "en", country: "United States" },
};

export const DEFAULT_MARKET: Market = { location_code: 2840, language_code: "en", country: "United States" };

export function marketFor(urlOrDomain: string | null | undefined): Market {
  const host = String(urlOrDomain || "")
    .trim()
    .toLowerCase()
    .replace(/^[a-z]+:\/\//, "")
    .replace(/[/?#:].*$/, "");
  const tld = host.split(".").filter(Boolean).pop() || "";
  return BY_CCTLD[tld] ?? DEFAULT_MARKET;
}
