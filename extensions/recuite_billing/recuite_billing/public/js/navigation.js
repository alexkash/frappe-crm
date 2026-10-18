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
  link.addEventListener("click", (event) => {
    const frm = window.cur_frm;
    if (
      event.button !== 0 ||
      event.ctrlKey ||
      event.metaKey ||
      event.shiftKey ||
      event.altKey ||
      frappe.get_route()[0] !== "Form" ||
      !frm?.is_dirty()
    )
      return;
    event.preventDefault();
    frappe.confirm("Є незбережені зміни. Повернутися до CRM без збереження?", () => {
      // Discarding was confirmed above; avoid a second browser warning.
      window.removeEventListener("beforeunload", frm.beforeUnloadListener, { capture: true });
      window.location.assign(link.href);
    });
  });
  home.after(link);
});
