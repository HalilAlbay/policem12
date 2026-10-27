self.addEventListener('push', event => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (_) {}
  const days = Number(data.days_before);
  const body = [30, 15, 7, 1].includes(days)
    ? 'Takibinizdeki bir poliçenin bitişine ' + days + ' gün kaldı.'
    : 'Yeni yenileme hatırlatmanız var.';
  event.waitUntil(self.registration.showNotification('Poliçem', {
    body: body,
    tag: 'policem-' + String(data.notification_id || 'general'),
    data: {url:'/'}
  }));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(clients.openWindow('/'));
});
