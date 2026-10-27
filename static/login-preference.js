(() => {
  function setShown(node, shown) { if (node) node.classList.toggle('hidden', !shown); }
  async function refreshLoginMethodUI() {
    const methodBox = document.getElementById('selectedLoginMethod');
    let method = 'password';
    try {
      const id = window.policeInstallationId?.();
      if (id) {
        const res = await fetch('/api/security/login-method?installation_id=' + encodeURIComponent(id));
        if (res.ok) method = (await res.json()).method || 'password';
      }
    } catch (_) { /* Offline or unknown selection safely shows password login. */ }
    if (methodBox) methodBox.textContent = 'Bu cihazdaki seçili yöntem: ' + ({pin:'4 haneli PIN',webauthn:'Face ID / cihaz doğrulaması',password:'Hesap şifresi'}[method] || 'Hesap şifresi');

    const login = document.getElementById('loginView');
    if (login) {
      const username = document.getElementById('username'), password = document.getElementById('password');
      const passwordButton = login.querySelector('button[onclick="login()"]');
      const passkeyButton = document.getElementById('passkeyLoginButton');
      const pinArea = document.getElementById('pinUnlockArea');
      const fallback = document.getElementById('passwordFallbackButton');
      const quick = method === 'pin' || method === 'webauthn';
      if (username) setShown(username.previousElementSibling, !quick);
      setShown(username, !quick); setShown(password?.previousElementSibling, !quick); setShown(password, !quick);
      setShown(passwordButton, !quick);
      setShown(passkeyButton, method === 'webauthn');
      setShown(pinArea, method === 'pin' && !!localStorage.getItem('policem_pin_device_id'));
      if (quick && !fallback) {
        const b=document.createElement('button');b.id='passwordFallbackButton';b.className='ghost';b.textContent='Hesap şifresiyle giriş';
        b.onclick=()=>{setShown(username.previousElementSibling,true);setShown(username,true);setShown(password.previousElementSibling,true);setShown(password,true);setShown(passwordButton,true);setShown(b,false)};
        document.getElementById('passkeyLoginButton')?.after(b);if(method==='pin')pinArea?.after(b);
      } else if (fallback) setShown(fallback, quick);
    }
    return method;
  }
  function setupPreferenceSettings() {
    const card = document.getElementById('settings')?.firstElementChild;
    if (card && !document.getElementById('selectedLoginMethod')) {
      const status=document.createElement('p');status.id='selectedLoginMethod';status.className='notice';
      const title=card.querySelector('h2');title?.after(status);
    }
    refreshLoginMethodUI();
  }
  window.refreshLoginMethodUI = refreshLoginMethodUI;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', setupPreferenceSettings, {once:true});
  else setupPreferenceSettings();
  if (window.sessionStorage?.getItem('policem_token')) setTimeout(refreshLoginMethodUI, 0);
})();
