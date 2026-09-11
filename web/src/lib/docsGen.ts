// Pure helpers that parse a FastAPI /openapi.json document into UI-ready shapes.
// Intentionally minimal: no $ref resolution, no allOf/oneOf flattening, no
// remote-schema fetching. Inline schemas only — anything else falls back to a
// free-form text input.

export type HttpMethod = "get" | "post" | "put" | "patch" | "delete";

export const HTTP_METHODS: HttpMethod[] = [
  "get",
  "post",
  "put",
  "patch",
  "delete",
];

// --- Raw OpenAPI shapes (only the bits we actually read) ---

export type OpenAPISchema = {
  type?: string;
  format?: string;
  enum?: (string | number | boolean)[];
  default?: unknown;
  example?: unknown;
  description?: string;
  properties?: Record<string, OpenAPISchema>;
  required?: string[];
  items?: OpenAPISchema;
};

export type OpenAPIParameter = {
  name: string;
  in: "path" | "query" | "header" | "cookie";
  required?: boolean;
  description?: string;
  schema?: OpenAPISchema;
};

export type OpenAPIRequestBody = {
  description?: string;
  required?: boolean;
  content?: Record<string, { schema?: OpenAPISchema }>;
};

export type OpenAPIOperation = {
  summary?: string;
  description?: string;
  operationId?: string;
  tags?: string[];
  parameters?: OpenAPIParameter[];
  requestBody?: OpenAPIRequestBody;
};

export type OpenAPIDocument = {
  paths?: Record<string, Partial<Record<HttpMethod, OpenAPIOperation>>>;
};

// --- UI-facing shapes ---

export type InputFieldKind = "text" | "number" | "boolean" | "json" | "longtext";

export type InputField = {
  name: string;
  in: "path" | "query" | "header" | "body";
  required: boolean;
  type: InputFieldKind;
  description?: string;
  example?: string;
  default?: string;
  enum?: (string | number | boolean)[];
};

export type Endpoint = {
  method: HttpMethod;
  path: string;
  summary: string;
  description: string;
  tags: string[];
  operationId: string;
  parameters: OpenAPIParameter[];
  requestBody: OpenAPIRequestBody | null;
  group: string;
};

// --- Constants for method display ---

export const METHOD_COLORS: Record<HttpMethod, string> = {
  get: "var(--info)",
  post: "var(--success)",
  put: "var(--warn)",
  patch: "var(--warn)",
  delete: "var(--danger)",
};

export const METHOD_LABEL: Record<HttpMethod, string> = {
  get: "GET",
  post: "POST",
  put: "PUT",
  patch: "PATCH",
  delete: "DELETE",
};

// --- Parsing ---

export function parseEndpoints(doc: OpenAPIDocument | null | undefined): Endpoint[] {
  const paths = doc?.paths;
  if (!paths || typeof paths !== "object") return [];

  const out: Endpoint[] = [];
  for (const [pathStr, methods] of Object.entries(paths)) {
    if (!methods || typeof methods !== "object") continue;
    for (const m of HTTP_METHODS) {
      const op = methods[m];
      if (!op) continue;
      const tags = Array.isArray(op.tags) ? op.tags.filter(Boolean) : [];
      out.push({
        method: m,
        path: pathStr,
        summary: op.summary ?? "",
        description: op.description ?? "",
        tags,
        operationId: op.operationId ?? "",
        parameters: Array.isArray(op.parameters) ? op.parameters : [],
        requestBody: op.requestBody ?? null,
        group: deriveGroup(pathStr, tags),
      });
    }
  }
  // Stable, friendly ordering: by group then path then method.
  out.sort((a, b) => {
    if (a.group !== b.group) return a.group.localeCompare(b.group);
    if (a.path !== b.path) return a.path.localeCompare(b.path);
    return HTTP_METHODS.indexOf(a.method) - HTTP_METHODS.indexOf(b.method);
  });
  return out;
}

function deriveGroup(pathStr: string, tags: string[]): string {
  if (tags.length > 0) return tags[0];
  // First non-empty segment after stripping leading slash.
  const parts = pathStr.split("/").filter(Boolean);
  if (parts.length === 0) return "(root)";
  // Strip a leading "api" segment if present so /api/agents groups as "agents".
  if (parts[0] === "api" && parts.length > 1) return parts[1];
  return parts[0];
}

export function groupByTag(endpoints: Endpoint[]): Record<string, Endpoint[]> {
  const groups: Record<string, Endpoint[]> = {};
  for (const ep of endpoints) {
    const g = ep.group || "(other)";
    if (!groups[g]) groups[g] = [];
    groups[g].push(ep);
  }
  return groups;
}

// --- Input field generation from OpenAPI shapes ---

export function getParameterInputs(parameters: OpenAPIParameter[] | undefined): InputField[] {
  if (!Array.isArray(parameters)) return [];
  const out: InputField[] = [];
  for (const p of parameters) {
    if (!p || typeof p !== "object") continue;
    const loc = p.in;
    if (loc !== "path" && loc !== "query" && loc !== "header") continue;
    out.push({
      name: p.name,
      in: loc,
      required: Boolean(p.required) || loc === "path",
      type: inputKindForSchema(p.schema),
      description: p.description,
      example: stringifyExample(p.schema?.default ?? p.schema?.example),
      default: p.schema?.default != null ? String(p.schema.default) : undefined,
      enum: Array.isArray(p.schema?.enum) ? p.schema!.enum : undefined,
    });
  }
  return out;
}

export function getRequestBodySchema(
  requestBody: OpenAPIRequestBody | null | undefined
): InputField[] | null {
  if (!requestBody || !requestBody.content) return null;
  // Prefer JSON; fall back to the first available content type.
  const json = requestBody.content["application/json"];
  const fallback = json ?? Object.values(requestBody.content)[0];
  const schema = fallback?.schema;
  if (!schema || schema.type !== "object" || !schema.properties) {
    // Non-object body (string/number/array) — expose a single JSON textarea.
    return [
      {
        name: "body",
        in: "body",
        required: Boolean(requestBody.required),
        type: "json",
        description: requestBody.description,
      },
    ];
  }
  const required = new Set(Array.isArray(schema.required) ? schema.required : []);
  const out: InputField[] = [];
  for (const [name, propSchema] of Object.entries(schema.properties)) {
    out.push({
      name,
      in: "body",
      required: required.has(name),
      type: inputKindForSchema(propSchema),
      description: propSchema?.description,
      example: stringifyExample(propSchema?.default ?? propSchema?.example),
      default: propSchema?.default != null ? String(propSchema.default) : undefined,
      enum: Array.isArray(propSchema?.enum) ? propSchema.enum : undefined,
    });
  }
  return out;
}

function inputKindForSchema(schema: OpenAPISchema | undefined): InputFieldKind {
  if (!schema || typeof schema !== "object") return "text";
  const t = schema.type;
  if (Array.isArray(schema.enum) && schema.enum.length > 0) return "text";
  if (t === "integer" || t === "number") return "number";
  if (t === "boolean") return "boolean";
  if (t === "array" || t === "object") return "json";
  if (t === "string") {
    const f = schema.format ?? "";
    if (f === "long" || f.includes("long-text")) return "longtext";
    return "text";
  }
  return "text";
}

function stringifyExample(v: unknown): string | undefined {
  if (v == null) return undefined;
  if (typeof v === "string") return v;
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}
