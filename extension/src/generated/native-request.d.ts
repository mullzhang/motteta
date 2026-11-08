/* Generated from schemas/native-request.schema.json. Do not edit. */

export type SchemaVersion = 1;
export type RequestId = string;
export type Operation = "check" | "status";
export type SchemaVersion1 = 1;
export type Title = string | null;
export type Authors = string[];
export type Isbn = string | null;
export type Namespace = string;
export type Scope = string;
export type Value = string;
export type Identifiers = Identifier[];
export type Format = "print" | "digital" | "unknown";
export type Volume = string | null;
export type Edition = string | null;
export type Language = string | null;
export type Url = string | null;

export interface NativeRequest {
  schema_version: SchemaVersion;
  request_id: RequestId;
  operation: Operation;
  candidate?: Candidate | null;
}
export interface Candidate {
  schema_version: SchemaVersion1;
  title?: Title;
  authors?: Authors;
  isbn?: Isbn;
  identifiers?: Identifiers;
  format: Format;
  volume?: Volume;
  edition?: Edition;
  language?: Language;
  url?: Url;
}
export interface Identifier {
  namespace: Namespace;
  scope: Scope;
  value: Value;
}
