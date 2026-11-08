import { adapters } from "../generated/adapters";
import { createAdapterRegistry } from "./registry";

export const { productAt, extractCandidate, insertionAnchor } = createAdapterRegistry(adapters);
