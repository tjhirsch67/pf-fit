// PF Coach frontend configuration.
// The backend is bearer-authenticated with permissive CORS, so the PWA calls Railway
// directly (no Netlify proxy needed — there are no cross-site cookies).
window.PF_CONFIG = {
  API_BASE: "https://pf-fit-production.up.railway.app",
};
