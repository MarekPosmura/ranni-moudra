// Veřejná konfigurace stránky. Tyto hodnoty SMÍ být veřejné:
// anon klíč je díky Row Level Security jen pro čtení (SELECT).
// NIKDY sem nedávej service_role klíč ani Anthropic klíč!
window.RM_CONFIG = {
  // Zkopíruj z Supabase -> Project Settings -> API
  SUPABASE_URL: "https://lqrambwhpvraldswewog.supabase.co",
  SUPABASE_ANON_KEY: "sb_publishable_t55sL4fI6PQcrpYQ6u9ijg_A_wH4Mi6",
};
