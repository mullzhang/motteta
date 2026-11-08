import type { Candidate } from "../generated/native-request";

export interface AdapterSettings {
  readonly id: string;
  readonly matches: readonly string[];
  readonly scope: string;
  readonly anchorSelector: string;
}

export interface ProductIdentity { scope: string; id: string }
export type Product = ProductIdentity & { source: string };
export type BookDetails = Omit<Candidate, "schema_version" | "identifiers" | "url"> & { title: string };
export interface Extraction { product: ProductIdentity; book: BookDetails }

export interface AdapterHandler {
  productAt(url: URL, settings: AdapterSettings): ProductIdentity | null;
  extract(doc: Document, url: URL, product: ProductIdentity): Extraction | null;
}

export interface ServiceAdapter {
  readonly settings: AdapterSettings;
  readonly handler: AdapterHandler;
}
