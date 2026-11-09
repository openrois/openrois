export function Footer() {
  return (
    <footer className="footer">
      <span>
        OpenRoIS · Apache-2.0 ·{" "}
        <a href="https://openrois.org" target="_blank" rel="noreferrer">
          openrois.org →
        </a>
      </span>
      <span className="end">@openrois/sdk {__SDK_VERSION__} · JSON-RPC 2.0 over WebSocket</span>
    </footer>
  );
}
