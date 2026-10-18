$(document).on("app_ready", () => {
  const home = document.querySelector(".navbar-home");
  if (!home || document.getElementById("ua-billing-crm-return")) return;
  const link = document.createElement("a");
  link.id = "ua-billing-crm-return";
  link.href = "/crm/billing";
  link.textContent = "← CRM";
  link.title = "Повернутися до документів CRM";
  link.setAttribute("aria-label", link.title);
  link.className = "btn btn-default btn-sm mr-3 flex-shrink-0";
  // A normal link preserves Frappe's native warning about unsaved changes.
  home.after(link);
});
