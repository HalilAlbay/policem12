// Runs only after an explicit user click on the notification settings button.
function policemVapidBytes(base64) {
  const s = (base64 + '='.repeat((4 - base64.length % 4) % 4)).replace(/-/g, '+').replace(/_/g, '/');
  return Uint8Array.from(atob(s), c => c.charCodeAt(0));
}
async function policemEnablePush() {
  if (!window.isSecureContext || !('serviceWorker' in navigator) || !('PushManager' in window))
    throw Error('Bu cihazda güvenli bağlantı üzerinden bildirim desteği bulunamadı.');
  const cfg = await api('push/config');
  if (!cfg.enabled) throw Error('Sunucuda bildirim anahtarları henüz ayarlanmadı.');
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') throw Error('Bildirim izni verilmedi.');
  const registration = await navigator.serviceWorker.register('/static/push-sw.js', {scope:'/static/'});
  const sub = await registration.pushManager.subscribe({
    userVisibleOnly:true, applicationServerKey:policemVapidBytes(cfg.public_key)
  });
  await api('push/subscribe', 'POST', sub.toJSON());
  return 'Bildirimler bu cihazda etkinleştirildi.';
}
async function policemDisablePush() {
  const registration = await navigator.serviceWorker.getRegistration('/static/');
  const sub = registration && await registration.pushManager.getSubscription();
  if (!sub) return 'Bu cihazda aktif bildirim bulunmuyor.';
  await api('push/unsubscribe', 'POST', sub.toJSON());
  await sub.unsubscribe();
  return 'Bu cihazda bildirimler kapatıldı.';
}
function policemPushControls() {
  if (document.getElementById('policem-push-settings')) return;
  const target = document.getElementById('settings');
  if (!target) return;
  const box = document.createElement('div');
  box.id='policem-push-settings'; box.className='card';
  const heading=document.createElement('h2');heading.textContent='Telefon bildirimleri';
  const note=document.createElement('p');note.className='muted';
  note.textContent='iPhone: Safari üzerinden ana ekrana eklenen uygulamayı açın. Bildirim izni yalnızca siz isterseniz sorulur.';
  const status=document.createElement('p');status.setAttribute('role','status');
  for (const [title, action] of [['Bildirimleri aç',policemEnablePush],['Bu cihazda kapat',policemDisablePush]]) {
    const btn=document.createElement('button');btn.textContent=title;
    btn.style.marginRight='8px';
    btn.addEventListener('click', async()=>{try{status.textContent=await action()}catch(e){status.textContent=e.message}});
    box.appendChild(btn);
  }
  const testBtn=document.createElement('button');
  testBtn.textContent='Test bildirimi gönder';
  testBtn.style.marginTop='8px';
  testBtn.addEventListener('click',async()=>{
    try {
      const cfg=await api('push/config');
      if(!cfg.test_enabled) throw Error('Test gönderimi bu ortamda kapalı.');
      const result=await api('push/test','POST',{});
      status.textContent='Test bildirimi gönderildi ('+result.sent+' cihaz).';
    } catch(e) {status.textContent=e.message;}
  });
  box.prepend(heading,note);box.appendChild(testBtn,status);target.appendChild(box);
}
document.addEventListener('DOMContentLoaded',()=>{const timer=setInterval(()=>{
  if(document.getElementById('settings')){clearInterval(timer);policemPushControls();}
},150);});

/* Re-register an existing opt-in subscription on authenticated app boot.
   Never request permission automatically and never create a subscription without consent. */
async function policemSyncExistingPush() {
  if (!('serviceWorker' in navigator) || !('Notification' in window) ||
      Notification.permission !== 'granted') return;
  const registration = await navigator.serviceWorker.getRegistration('/static/');
  if (!registration) return;
  const sub = await registration.pushManager.getSubscription();
  if (!sub) return;
  const cfg = await api('push/config');
  if (!cfg.test_enabled) return;
  await api('push/subscribe', 'POST', sub.toJSON());
  // Policy expiry notifications are delivered by the server schedule.
}
let policemPushBootTriggered = false;
const policemPushBootObserver = new MutationObserver(() => {
  const app = document.getElementById('appView');
  if (!app || app.classList.contains('hidden')) {
    policemPushBootTriggered = false;
    return;
  }
  if (policemPushBootTriggered) return;
  policemPushBootTriggered = true;
  policemSyncExistingPush().catch(e => console.warn('Automatic push test failed:', e.message));
});
document.addEventListener('DOMContentLoaded', () => {
  policemPushBootObserver.observe(document.body, {subtree:true,attributes:true,attributeFilter:['class']});
  policemPushBootObserver.takeRecords();
  if (document.getElementById('appView') && !document.getElementById('appView').classList.contains('hidden')) {
    policemPushBootTriggered = true;
    policemSyncExistingPush().catch(e => console.warn('Automatic push test failed:', e.message));
  }
});
