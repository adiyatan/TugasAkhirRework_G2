import { fetchMenuPlaceholder, renderPlaceholderCard } from "./shared.js";

export async function renderInputStrukMenu(container, { user, navigateTo, onUnauthorized }) {
  const message = await fetchMenuPlaceholder("/struk", onUnauthorized);
  const canGoHome = user.allowed_menus.includes("home");

  container.replaceChildren(
    renderPlaceholderCard({
      badgeText: "Tab Input Struk",
      title: "Input Struk Transaksi",
      message,
      theme: "amber",
      iconSvg: `
        <svg class="w-7 h-7" fill="none" stroke="currentColor" stroke-width="1.9" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h4M7 3h10a2 2 0 0 1 2 2v16l-3-2-2 2-2-2-2 2-2-2-3 2V5a2 2 0 0 1 2-2Z" />
        </svg>
      `,
      onBackHome: canGoHome ? () => navigateTo("home") : null,
    })
  );
}
