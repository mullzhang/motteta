export interface CompiledPattern {
  readonly hostPermission: string;
  matches(url: URL): boolean;
}

/** Supported Chrome patterns: HTTPS, an exact host or *.host, and path wildcards. */
export function compileMatchPattern(pattern: string): CompiledPattern {
  const parts = pattern.match(/^https:\/\/(\*\.)?([a-z0-9.-]+)(?::(\*|\d+))?(\/[^\s#]*)$/);
  if (!parts || !parts[2].split(".").every(label => /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(label))) {
    throw new Error(`Invalid HTTPS adapter match pattern: ${pattern}`);
  }
  const [, wildcard, host, port, path] = parts;
  if (port && port !== "*" && (Number(port) < 1 || Number(port) > 65535)) throw new Error(`Invalid port in adapter match pattern: ${pattern}`);
  const pathRegex = new RegExp("^" + path.split("*").map(part => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join(".*") + "$");
  return {
    hostPermission: `https://${wildcard ?? ""}${host}${port ? ":" + port : ""}/*`,
    matches(url: URL): boolean {
      return url.protocol === "https:" &&
        (url.hostname === host || Boolean(wildcard && url.hostname.endsWith("." + host))) &&
        (!port || port === "*" || Number(url.port || "443") === Number(port)) &&
        pathRegex.test(url.pathname + url.search);
    }
  };
}
