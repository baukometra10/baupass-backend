export const INTEGRATION_WIZARD = {
  sap: {
    title: "SAP",
    fields: [
      { key: "endpoint", label: "SAP API URL", type: "url", required: true },
      { key: "apiKey", label: "API Key", type: "password" },
      { key: "clientId", label: "Client ID", type: "text" },
    ],
  },
  oracle: {
    title: "Oracle",
    fields: [
      { key: "endpoint", label: "Oracle REST URL", type: "url", required: true },
      { key: "apiKey", label: "API Key", type: "password" },
    ],
  },
  microsoft365: {
    title: "Microsoft 365",
    oauth: true,
    fields: [
      { key: "tenant_id", label: "Tenant ID", type: "text", required: true },
      { key: "client_id", label: "Client ID", type: "text", required: true },
      { key: "client_secret", label: "Client Secret", type: "password", required: true },
    ],
  },
  google_workspace: {
    title: "Google Workspace",
    oauth: true,
    fields: [
      { key: "client_id", label: "OAuth Client ID", type: "text", required: true },
      { key: "client_secret", label: "Client Secret", type: "password", required: true },
    ],
  },
  payroll: {
    title: "Payroll",
    fields: [
      { key: "endpoint", label: "Export URL", type: "url" },
      { key: "apiKey", label: "API Key", type: "password" },
    ],
  },
};

export function buildConnectPayload(provider, formData) {
  const spec = INTEGRATION_WIZARD[provider];
  if (!spec) return {};
  const body = {};
  const oauth = {};
  spec.fields.forEach((f) => {
    const v = formData.get(f.key);
    if (v == null || v === "") return;
    if (spec.oauth) oauth[f.key] = v;
    else body[f.key] = v;
  });
  if (spec.oauth && Object.keys(oauth).length) return { oauth };
  return body;
}

export function renderWizardForm(provider, formEl) {
  const spec = INTEGRATION_WIZARD[provider];
  if (!spec || !formEl) return;
  formEl.innerHTML = spec.fields
    .map(
      (f) => `
    <label>
      <span>${f.label}</span>
      <input name="${f.key}" type="${f.type || "text"}" ${f.required ? "required" : ""} />
    </label>`
    )
    .join("");
}
