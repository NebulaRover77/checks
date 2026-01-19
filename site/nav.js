const navRoot = document.getElementById("top-nav");

if (navRoot) {
  navRoot.innerHTML = `
    <nav class="nav">
      <div class="logo">CheckCraft</div>
      <div class="nav-links">
        <a href="/generate_check.html">Print on checks</a>
        <a href="/blank_checks.html">Blank checks</a>
        <a href="/settings.html">Settings</a>
        <a href="/login">SSO Login</a>
      </div>
    </nav>
  `;
}
