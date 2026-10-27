(() => {
  const $ = id => document.getElementById(id);
  async function requestPasswordReset() {
    const email = prompt('Hesabınızın e-posta adresini yazın:');
    if (email === null) return;
    try {
      const result = await api('account/password-reset/request', 'POST', { email });
      $('loginStatus').textContent = result.message;
    } catch (e) { $('loginStatus').textContent = e.message==='İşlem başarısız'?'E-posta gönderimi şu anda kullanılamıyor.':e.message; }
  }
  async function requestEmailVerification() {
    const email = $('accountEmail').value.trim();
    const password = prompt('E-posta adresini doğrulama bağlantısı göndermek için şifrenizi girin:');
    if (password === null) return;
    try {
      const result = await api('account/email/verification/request', 'POST', { email, password });
      $('accountEmailStatus').textContent = result.message;
    } catch (e) { $('accountEmailStatus').textContent = e.message==='İşlem başarısız'?'E-posta gönderimi şu anda kullanılamıyor.':e.message; }
  }
  async function refreshAccountEmailUI() {
    const box = $('accountEmailCard');
    if (!box || !token) return;
    try {
      const status = await api('account/email/status');
      $('accountEmail').value = status.email || '';
      $('accountEmailStatus').textContent = status.verified
        ? 'E-posta doğrulandı.'
        : status.email_available
          ? 'E-posta doğrulanmadı. Doğrulama bağlantısı isteyin.'
          : 'E-posta hizmeti ayarlı değil; doğrulama ve e-posta ile şifre sıfırlama kullanılamıyor.';
      $('verifyEmailButton').disabled = !status.email_available;
    } catch (_) { /* Retain the last locally rendered status. */ }
  }
  async function handleOneTimeLink() {
    const fragment = location.hash.slice(1);
    const match = /^(verify-email|reset-password)=([A-Za-z0-9_-]{32,128})$/.exec(fragment);
    if (!match) return;
    const [, kind, value] = match;
    history.replaceState({}, '', location.pathname + location.search);
    $('loginView').classList.remove('hidden');
    $('setupView').classList.add('hidden');
    try {
      if (kind === 'verify-email') {
        await api('account/email/verification/complete', 'POST', { token: value });
        $('loginStatus').textContent = 'E-posta adresi doğrulandı. Şifrenizle giriş yapabilirsiniz.';
      } else {
        const password = prompt('Yeni şifrenizi girin (en az 12 karakter):');
        if (password === null) return;
        const confirmPassword = prompt('Yeni şifrenizi tekrar girin:');
        if (confirmPassword === null) return;
        if (password.length < 12 || password !== confirmPassword) throw Error('Yeni şifreler aynı ve en az 12 karakter olmalıdır.');
        await api('account/password-reset/complete', 'POST', { token: value, password });
        $('loginStatus').textContent = 'Şifre sıfırlandı. Yeni şifrenizle giriş yapın.';
      }
    } catch (e) { $('loginStatus').textContent = e.message; }
  }
  function setup() {
    const login = $('loginView');
    if (login && !$('emailPasswordResetButton')) {
      const button = document.createElement('button'); button.id='emailPasswordResetButton';
      button.className='ghost'; button.textContent='E-postayla şifre sıfırlama'; button.onclick=requestPasswordReset;
      login.querySelector('h1')?.after(button);
    }
    const settings = $('settings');
    if (settings && !$('accountEmailCard')) {
      const card=document.createElement('div'); card.id='accountEmailCard'; card.className='card';
      card.innerHTML='<h2>E-posta doğrulama ve şifre kurtarma</h2><p id="accountEmailStatus" class="muted"></p><label for="accountEmail">E-posta adresi</label><input id="accountEmail" type="email" maxlength="254" autocomplete="email"><p><button id="verifyEmailButton">Doğrulama bağlantısı gönder</button></p><p class="muted">E-posta ile sıfırlama yalnızca doğrulanmış adreslerde kullanılabilir. Kayıp telefon için acente yetkilisinin verdiği geçici şifre akışı ayrıdır.</p>';
      $('brandingSettings')?.before(card);
      $('verifyEmailButton').onclick=requestEmailVerification;
    }
    handleOneTimeLink();
  }
  window.refreshAccountEmailUI=refreshAccountEmailUI;
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',setup,{once:true});else setup();
})();
