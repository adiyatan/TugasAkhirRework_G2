import { fetchMenuPlaceholder, renderPlaceholderCard } from "./shared.js";

export async function renderInputMutasiMenu(container, { navigateTo, onUnauthorized }) {
  const message = await fetchMenuPlaceholder("/mutasi", onUnauthorized);

  container.replaceChildren(
    renderPlaceholderCard({
      badgeText: "Tab Input Mutasi",
      title: "Impor Mutasi Rekening",
      message,
      theme: "emerald",
      iconSvg: `
        <svg class="w-7 h-7" fill="none" stroke="currentColor" stroke-width="1.9" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 16V4m0 0l-4 4m4-4l4 4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
        </svg>
      `,
      onBackHome: () => navigateTo("home"),
    })
  );
}
