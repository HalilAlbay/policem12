/* PIN mode uses a per-browser, non-extractable ECDSA key as possession proof. */
(() => {
  const DB_NAME = 'policem-device-proof-v1';
  const STORE = 'keys';
  const DEVICE_KEY = 'policem_pin_device_id';
  const enc = new TextEncoder();
  const b64 = bytes => btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
  const un64 = s => {
    const raw = atob(s.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - s.length % 4) % 4));
    return Uint8Array.from(raw, c => c.charCodeAt(0));
  };
  function db() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  async function keyStore(mode, id, value) {
    const d = await db();
    return new Promise((resolve, reject) => {
      const tx = d.transaction(STORE, mode), store = tx.objectStore(STORE);
      const req = mode === 'readonly' ? store.get(id) : store.put(value, id);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
      tx.oncomplete = () => d.close();
      tx.onerror = () => reject(tx.error);
    });
  }
  async function sign(privateKey, purpose, ceremonyId, deviceId, challenge) {
    const message = new Uint8Array([
      ...enc.encode('policem-pin-v1\0'), ...enc.encode(purpose), 0,
      ...enc.encode(ceremonyId), 0, ...enc.encode(deviceId), 0, ...un64(challenge)
    ]);
    return b64(await crypto.subtle.sign({ name: 'ECDSA', hash: 'SHA-256' }, privateKey, message));
  }
  function bindButton(parent, label, callback, id) {
    if (document.getElementById(id)) return;
    const button = document.createElement('button');
    button.id = id; button.className = 'ghost'; button.textContent = label; button.onclick = callback;
    parent.append(button);
  }
  async function enrollPin() {
    await safe(async () => {
      if (!crypto?.subtle || !indexedDB) throw Error('Bu tarayıcı güvenli cihaz anahtarını saklayamıyor. Şifreyle giriş kullanın.');
      const pin = prompt('Yeni 4 haneli PIN’i girin:');
      if (pin === null) return;
      const confirmPin = prompt('PIN’i tekrar girin:');
      if (confirmPin === null) return;
      if (!/^\d{4}$/.test(pin) || pin !== confirmPin) throw Error('PIN’ler aynı ve dört rakam olmalıdır.');
      const label = $('quickDeviceName').value.trim();
      if (!label) throw Error('Önce cihaz adını yazın.');
      const begin = await api('security/pin/enroll/options', 'POST', { label, password: $('quickPassword').value });
      const pair = await crypto.subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, false, ['sign', 'verify']);
      const publicKey = await crypto.subtle.exportKey('jwk', pair.publicKey);
      await keyStore('readwrite', begin.device_id, pair.privateKey);
      try {
        const signature = await sign(pair.privateKey, 'enroll', begin.ceremony_id, begin.device_id, begin.challenge);
        await api('security/pin/enroll/verify', 'POST', {
          ceremony_id: begin.ceremony_id, device_id: begin.device_id, public_key: publicKey,
          pin, pin_confirm: confirmPin, signature
        });
        localStorage.setItem(DEVICE_KEY, begin.device_id);
        $('quickPassword').value = '';
        showPinUnlock();
        await loadSecurityDevices();
        msg('PIN ile güvenilir cihaz kaydedildi');
      } catch (error) {
        const d = await db(); d.transaction(STORE, 'readwrite').objectStore(STORE).delete(begin.device_id);
        throw error;
      }
    });
  }
  function showPinUnlock() {
    const area = document.getElementById('pinUnlockArea');
    if (area && localStorage.getItem(DEVICE_KEY)) area.classList.remove('hidden');
  }
  async function pinLogin() {
    await safe(async () => {
      const deviceId = localStorage.getItem(DEVICE_KEY);
      if (!deviceId) throw Error('Bu cihazda PIN kaydı bulunamadı. Şifreyle giriş yapın.');
      const privateKey = await keyStore('readonly', deviceId);
      if (!privateKey) throw Error('Cihaz anahtarı bulunamadı. Şifreyle giriş yapıp PIN’i yeniden kurun.');
      const pin = $('pinUnlockValue').value;
      if (!/^\d{4}$/.test(pin)) throw Error('Dört haneli PIN girin.');
      const begin = await api('security/pin/login/options', 'POST', { device_id: deviceId });
      const signature = await sign(privateKey, 'login', begin.ceremony_id, deviceId, begin.challenge);
      const result = await api('security/pin/login/verify', 'POST', {
        device_id: deviceId, ceremony_id: begin.ceremony_id, pin, signature
      });
      $('pinUnlockValue').value = '';
      token = result.token; user = result.user; sessionLocked = false; lastUserInteractionAt = Date.now();
      sessionStorage.setItem('policem_token', token);
      await boot();
    });
  }
  function setupPinUI() {
    const login = $('loginView');
    if (login && !document.getElementById('pinUnlockArea')) {
      const area = document.createElement('div'); area.id = 'pinUnlockArea'; area.className = 'hidden';
      area.innerHTML = '<label for="pinUnlockValue">4 haneli PIN</label><input id="pinUnlockValue" type="password" inputmode="numeric" pattern="[0-9]*" maxlength="4" autocomplete="one-time-code"><p><button id="pinLoginButton" class="ghost">PIN ile giriş</button></p>';
      $('passkeyLoginButton')?.after(area);
      document.getElementById('pinLoginButton').onclick = pinLogin;
    }
    const card = $('settings')?.firstElementChild;
    if (card && !document.getElementById('pinEnrollButton')) bindButton(card, 'PIN ile giriş ekle', enrollPin, 'pinEnrollButton');
    showPinUnlock();
  }
  window.enrollPin = enrollPin;
  window.pinLogin = pinLogin;
  setupPinUI();
  if (token) setTimeout(setupPinUI, 0);
})();
