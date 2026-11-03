(() => {
'use strict';

/* ------------------------------------------------------------------ i18n */
const I18N = {
  en: {
    app_title: 'Photo editor for property listings', sign_in: 'Sign in', sign_out: 'Sign out', username: 'Username', password: 'Password',
    login_bad: 'Wrong username or password.', login_locked: 'Too many attempts. Try again in {m} min.',
    step_mode: 'Choose an editing mode', step_add: 'Add photos',
    mode_natural: 'Natural', mode_premium: 'Premium Airbnb', mode_bright: 'Bright & Clean',
    mode_natural_d: 'Subtle exposure, colour, sharpness and noise improvements.',
    mode_premium_d: 'Bright, balanced, professional listing look with natural colours and excellent detail.',
    mode_bright_d: 'Brighter interiors, lifted shadows and clean whites without blowing out windows.',
    default: 'Default', mode_label: 'Mode',
    drop_title: 'Drag photos, folders or ZIP files here',
    drop_sub: 'Works straight from your external drive. Your original files are never changed.',
    btn_photos: 'Choose photos', btn_folder: 'Choose folder', btn_zip: 'Choose ZIP',
    limits: 'Up to {files} photos and {mb} MB per job · {fmb} MB per photo · JPG, PNG, WebP, TIFF, HEIC',
    jobs_title: 'Your jobs on the server', open: 'Open', photos_n: '{n} photos', min_left: '{m} min left',
    job_heading: '{n} photos', add_more: 'Add more photos', delete_job: 'Delete job',
    confirm_delete: 'Delete this job and all its photos from the server?',
    start: 'Edit {n} photos', start_one: 'Edit 1 photo',
    uploading: 'Uploading {done} of {total}…', upload_done: 'Upload complete',
    preparing: 'Preparing {n} photos…', processing: 'Editing: {done} of {total} done', all_done: 'All photos edited',
    s_uploaded: 'Waiting', s_analyzing: 'Preparing', s_ready: 'Ready', s_queued: 'Queued', s_processing: 'Editing…', s_done: 'Done', s_failed: 'Failed',
    download_all: 'Download all (ZIP)', download: 'Download', reedit: 'Re-edit this photo', reedit_all_label: 'Re-edit all photos with', apply: 'Apply',
    dl_started: 'Download started. When your ZIP has finished saving, remove the photos from the server.',
    delete_now: 'Delete from server now',
    retention: 'Photos are deleted from the server automatically in {m} min. Originals on your drive are never modified.',
    before: 'Before', after: 'After', compare_pending: 'This photo has not been edited yet.',
    ignored: '{n} unsupported files were ignored.', failed_n: '{n} photos could not be processed — see the red labels.',
    upload_failed: '{n} files could not be uploaded: {why}',
    too_big: '{name} is larger than {mb} MB and was skipped.',
    err_generic: 'Something went wrong. Please try again.', err_network: 'Network problem. Check your connection and try again.',
    err_job_not_found: 'This job no longer exists (it expired or was deleted).',
    err_too_many_files: 'A job can hold only {files} photos. Process these first, then start a new job.',
    err_job_too_large: 'A job can hold only {mb} MB. Process these first, then start a new job.',
    err_file_too_large: 'A file is larger than the allowed size.', err_disk_full: 'The server is out of temporary space.',
    err_too_many_jobs: 'Too many open jobs. Delete a finished job first.',
    deleted: 'Job deleted from the server.', reprocess_queued: 'Re-editing queued.',
    outpath: 'Saved as', unit_s: 's',
    c_original: 'Original {n}', c_final: 'Final {n}', c_excluded: 'Excluded {n}', c_failed: 'Failed {n}',
    organizing: 'Getting the photos ready…',
    main_photo: 'Main photo', make_main: 'Make main photo', make_main_s: 'Make main', exclude: 'Exclude', restore: 'Restore',
    excluded_title: 'Excluded photos ({n})', ex_dup: 'Same shot as {name}: the better photo was kept', ex_user: 'Excluded by you',
    similar: 'Similar to another photo', unsure: 'Unsure', suggested_room: 'Suggested room: please check',
    drag_hint: 'Photos stay in file-name order. Drag to change it; photo 1 is the main photo.', reset_order: 'Suggested order', arranged_by_you: 'Arranged by you',
    pending_new: 'New photos (not arranged yet)', numbering: 'Add a number before each file name (01 - name). Off keeps the exact original names.',
    smart: 'Smart organise (optional)', smart_hint: 'Removes near-identical copies of the same shot and arranges the gallery for Airbnb. Off: every photo is kept, in the same order, with its exact file name.',
    reset_order_plain: 'Original order', already_n: '{n} photo(s) were already in this job and were not added a second time.',
    renamed_n: '{n} files had exactly the same path as a different file, so they got “(2)” in their name.', renamed_hint: 'Same path as another file, saved as: {name}',
    dl_zip: 'Download {name}', dl_log: 'Download log', earlier: 'Move earlier', later: 'Move later',
    ml_off: 'Room detection was not available, so photos stay in upload order. You can set each room type by hand.',
    compare_excluded: 'This photo is excluded, so it was not edited. Restore it to edit and include it.',
    room_living: 'Living room', room_bedroom: 'Bedroom', room_kitchen: 'Kitchen', room_bathroom: 'Bathroom', room_dining: 'Dining area',
    room_workspace: 'Workspace', room_balcony: 'Balcony', room_amenity: 'Amenity', room_view: 'View', room_exterior: 'Building exterior',
    room_entrance: 'Entrance / hallway', room_parking: 'Parking', room_other: 'Other', room_label: 'Room type',
    err_order_mismatch: 'The photo list changed. Please try again.', err_not_in_gallery: 'Restore this photo first.',
  },
  ar: {
    app_title: 'محرر صور العقارات', sign_in: 'تسجيل الدخول', sign_out: 'تسجيل الخروج', username: 'اسم المستخدم', password: 'كلمة المرور',
    login_bad: 'اسم المستخدم أو كلمة المرور غير صحيحة.', login_locked: 'محاولات كثيرة. حاول مجددًا بعد {m} دقيقة.',
    step_mode: 'اختر نمط التحرير', step_add: 'أضف الصور',
    mode_natural: 'طبيعي', mode_premium: 'بريميوم Airbnb', mode_bright: 'ساطع ونظيف',
    mode_natural_d: 'تحسينات خفيفة في الإضاءة والألوان والحدّة وتقليل التشويش.',
    mode_premium_d: 'مظهر احترافي ساطع ومتوازن لإعلانات الإيجار، بألوان طبيعية وتفاصيل ممتازة.',
    mode_bright_d: 'إضاءة أعلى للمساحات الداخلية وظلال أوضح وبياض نظيف دون حرق النوافذ.',
    default: 'الافتراضي', mode_label: 'النمط',
    drop_title: 'اسحب الصور أو المجلدات أو ملفات ZIP إلى هنا',
    drop_sub: 'يعمل مباشرةً من القرص الخارجي. لا يتم تعديل ملفاتك الأصلية أبدًا.',
    btn_photos: 'اختيار صور', btn_folder: 'اختيار مجلد', btn_zip: 'اختيار ملف ZIP',
    limits: 'حتى {files} صورة و{mb} ميغابايت لكل مهمة · {fmb} ميغابايت للصورة · JPG وPNG وWebP وTIFF وHEIC',
    jobs_title: 'مهامك على الخادم', open: 'فتح', photos_n: '{n} صورة', min_left: 'متبقي {m} دقيقة',
    job_heading: '{n} صورة', add_more: 'إضافة صور', delete_job: 'حذف المهمة',
    confirm_delete: 'هل تريد حذف هذه المهمة وجميع صورها من الخادم؟',
    start: 'حرّر {n} صورة', start_one: 'حرّر صورة واحدة',
    uploading: 'جارٍ الرفع {done} من {total}…', upload_done: 'اكتمل الرفع',
    preparing: 'جارٍ تحضير {n} صورة…', processing: 'جارٍ التحرير: اكتمل {done} من {total}', all_done: 'تم تحرير جميع الصور',
    s_uploaded: 'بالانتظار', s_analyzing: 'قيد التحضير', s_ready: 'جاهزة', s_queued: 'في الطابور', s_processing: 'جارٍ التحرير…', s_done: 'تم', s_failed: 'فشل',
    download_all: 'تحميل الكل (ZIP)', download: 'تحميل', reedit: 'إعادة تحرير هذه الصورة', reedit_all_label: 'إعادة تحرير كل الصور بنمط', apply: 'تطبيق',
    dl_started: 'بدأ التحميل. بعد اكتمال حفظ ملف ZIP، احذف الصور من الخادم.',
    delete_now: 'احذف من الخادم الآن',
    retention: 'تُحذف الصور من الخادم تلقائيًا بعد {m} دقيقة. ملفاتك الأصلية على القرص لا تتغير أبدًا.',
    before: 'قبل', after: 'بعد', compare_pending: 'لم يتم تحرير هذه الصورة بعد.',
    ignored: 'تم تجاهل {n} ملف (نوع غير مدعوم).', failed_n: 'تعذّرت معالجة {n} صورة — راجع العلامات الحمراء.',
    upload_failed: 'تعذّر رفع {n} ملف: {why}',
    too_big: 'الملف {name} أكبر من {mb} ميغابايت وتم تخطيه.',
    err_generic: 'حدث خطأ ما. حاول مرة أخرى.', err_network: 'مشكلة في الشبكة. تحقق من اتصالك وحاول مجددًا.',
    err_job_not_found: 'هذه المهمة لم تعد موجودة (انتهت صلاحيتها أو حُذفت).',
    err_too_many_files: 'تستوعب المهمة {files} صورة فقط. عالج هذه الصور أولًا ثم ابدأ مهمة جديدة.',
    err_job_too_large: 'تستوعب المهمة {mb} ميغابايت فقط. عالج هذه الصور أولًا ثم ابدأ مهمة جديدة.',
    err_file_too_large: 'حجم أحد الملفات أكبر من المسموح.', err_disk_full: 'لا توجد مساحة مؤقتة كافية على الخادم.',
    err_too_many_jobs: 'عدد المهام المفتوحة كبير. احذف مهمة منتهية أولًا.',
    deleted: 'تم حذف المهمة من الخادم.', reprocess_queued: 'تمت إضافة إعادة التحرير إلى الطابور.',
    outpath: 'يُحفظ باسم', unit_s: 'ث',
    c_original: 'الأصلية {n}', c_final: 'النهائية {n}', c_excluded: 'المستبعدة {n}', c_failed: 'الفاشلة {n}',
    organizing: 'جارٍ تجهيز الصور…',
    main_photo: 'الصورة الرئيسية', make_main: 'اجعلها الصورة الرئيسية', make_main_s: 'اجعلها رئيسية', exclude: 'استبعاد', restore: 'استعادة',
    excluded_title: 'الصور المستبعدة ({n})', ex_dup: 'نفس اللقطة مثل {name}: احتُفظ بالأفضل', ex_user: 'استبعدتها أنت',
    similar: 'تشبه صورة أخرى', unsure: 'غير مؤكد', suggested_room: 'غرفة مقترحة: يُرجى التأكد',
    drag_hint: 'تبقى الصور بترتيب أسماء الملفات. اسحب لتغيير الترتيب؛ الصورة رقم 1 هي الرئيسية.', reset_order: 'الترتيب المقترح', arranged_by_you: 'رتّبتها أنت',
    pending_new: 'صور جديدة (لم تُرتّب بعد)', numbering: 'إضافة رقم قبل اسم كل ملف (01 - الاسم). عند الإيقاف تبقى الأسماء الأصلية كما هي.',
    smart: 'تنظيم ذكي (اختياري)', smart_hint: 'يستبعد النسخ شبه المتطابقة من اللقطة نفسها ويرتّب المعرض لـ Airbnb. عند الإيقاف: تبقى كل الصور بنفس الترتيب وبأسمائها الأصلية تمامًا.',
    reset_order_plain: 'الترتيب الأصلي', already_n: '{n} صورة كانت موجودة في هذه المهمة ولم تُضَف مرة ثانية.',
    renamed_n: '{n} ملف له المسار نفسه تمامًا لملف مختلف، فأُضيفت «(2)» إلى اسمه.', renamed_hint: 'نفس مسار ملف آخر، حُفظ باسم: {name}',
    dl_zip: 'تحميل {name}', dl_log: 'تحميل السجل', earlier: 'قدّم', later: 'أخّر',
    ml_off: 'تعذّر التعرف على نوع الغرف، فبقيت الصور بترتيب الرفع. يمكنك تحديد نوع كل غرفة يدويًا.',
    compare_excluded: 'هذه الصورة مستبعدة ولذلك لم تُعدَّل. استعدها لتعديلها وإدراجها.',
    room_living: 'الصالة', room_bedroom: 'غرفة نوم', room_kitchen: 'مطبخ', room_bathroom: 'حمام', room_dining: 'منطقة الطعام',
    room_workspace: 'ركن عمل', room_balcony: 'شرفة', room_amenity: 'مرفق', room_view: 'إطلالة', room_exterior: 'واجهة المبنى',
    room_entrance: 'مدخل / ممر', room_parking: 'موقف', room_other: 'أخرى', room_label: 'نوع الغرفة',
    err_order_mismatch: 'تغيّرت قائمة الصور. حاول مرة أخرى.', err_not_in_gallery: 'استعد هذه الصورة أولًا.',
  },
};
const MODES = ['natural', 'premium', 'bright'];
const STORE = (() => { try { return window.localStorage; } catch { return null; } })();
let lang = (STORE && STORE.getItem('hpe_lang')) || ((navigator.language || '').toLowerCase().startsWith('ar') ? 'ar' : 'en');
const t = (k, v = {}) => String((I18N[lang][k] ?? I18N.en[k] ?? k)).replace(/\{(\w+)\}/g, (_, n) => (v[n] ?? ''));

/* ------------------------------------------------------------------ helpers */
const $ = (s, r = document) => r.querySelector(s);
const HDR = { 'X-Requested-With': 'roomlit' };
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v; else if (k.startsWith('on')) el.addEventListener(k.slice(2), v); else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c != null) el.append(c.nodeType ? c : document.createTextNode(c));
  return el;
}
class ApiError extends Error { constructor(status, code, message, data) { super(message); this.status = status; this.code = code; this.data = data; } }
function errText(e) {
  const k = 'err_' + e.code;
  if (I18N.en[k]) return t(k, { files: S.cfg?.max_files, mb: S.cfg?.max_job_mb });
  if (e.code === 'network') return t('err_network');
  return e.message || t('err_generic');
}
function toast(msg, bad = false) {
  const el = h('div', { class: 'toast' + (bad ? ' bad' : '') }, msg);
  $('#toasts').append(el); setTimeout(() => el.remove(), bad ? 7000 : 3500);
}
async function api(path, { method = 'GET', body } = {}) {
  const opt = { method, headers: { ...HDR }, credentials: 'same-origin' };
  if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  let r;
  try { r = await fetch('/api' + path, opt); } catch { throw new ApiError(0, 'network', t('err_network')); }
  let data = null; try { data = await r.json(); } catch { /* not json */ }
  if (r.status === 401 && path !== '/login') { showLogin(); throw new ApiError(401, 'unauthorized', ''); }
  if (!r.ok) throw new ApiError(r.status, data && data.error, data && data.message, data);
  return data;
}
const fmtMB = (b) => (b / 1e6 >= 10 ? Math.round(b / 1e6) : (b / 1e6).toFixed(1)) + ' MB';

/* ------------------------------------------------------------------ state */
const S = { cfg: null, job: null, rev: 0, mode: 'premium', timer: null, sig: '', cards: new Map(), modalId: null,
  up: null, clickedZip: false, clientIgnored: 0, user: null, drag: null,
  numbering: (() => { try { return localStorage.getItem('rl_num2') === '1'; } catch { return false; } })(),
  smart: (() => { try { return localStorage.getItem('rl_smart') === '1'; } catch { return false; } })(), openEx: {} };
const ALLOWED = new Set(['.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff', '.heic', '.heif']);
const extOf = (n) => { const i = n.lastIndexOf('.'); return i < 0 ? '' : n.slice(i).toLowerCase(); };
const isJunk = (p) => p.split('/').some((c) => c.startsWith('.') || c.toLowerCase() === '__macosx') || /(^|\/)(thumbs\.db|desktop\.ini)$/i.test(p);

/* ------------------------------------------------------------------ language */
function applyLang() {
  document.documentElement.lang = lang; document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
  $('#btn-lang').textContent = lang === 'ar' ? 'English' : 'العربية';
  document.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
  $('#tag-before').textContent = t('before'); $('#tag-after').textContent = t('after');
  renderModes(); renderLimits(); fillModeSelect($('#reedit-mode')); fillModeSelect($('#m-mode'));
  if (S.job) { S.sig = ''; S.cards.clear(); renderJob(); renderModal(); } else renderOldJobs();
}
$('#btn-lang').addEventListener('click', () => { lang = lang === 'ar' ? 'en' : 'ar'; if (STORE) STORE.setItem('hpe_lang', lang); applyLang(); });

/* ------------------------------------------------------------------ login / session */
function showLogin() {
  stopPolling(); $('#view-app').classList.add('hidden'); $('#view-login').classList.remove('hidden'); $('#btn-logout').classList.add('hidden');
  $('#login-pass').value = '';
}
async function showApp() {
  $('#view-login').classList.add('hidden'); $('#view-app').classList.remove('hidden'); $('#btn-logout').classList.remove('hidden');
  S.cfg = await api('/config'); S.mode = S.cfg.default_mode; applyLang();
  const { jobs } = await api('/jobs');
  S.oldJobs = jobs;
  if (jobs.length) await openJob(jobs[0].id); else showStart();
}
$('#login-form').addEventListener('submit', async (e) => {
  e.preventDefault(); const err = $('#login-error'); err.classList.add('hidden');
  try {
    await api('/login', { method: 'POST', body: { username: $('#login-user').value, password: $('#login-pass').value } });
    await showApp();
  } catch (ex) {
    err.textContent = ex.code === 'locked' ? t('login_locked', { m: Math.ceil(((ex.data && ex.data.retry_after) || 900) / 60) }) : (ex.status === 401 ? t('login_bad') : errText(ex));
    err.classList.remove('hidden');
  }
});
$('#btn-logout').addEventListener('click', async () => { try { await api('/logout', { method: 'POST' }); } catch { /* ignore */ } S.job = null; showLogin(); });

/* ------------------------------------------------------------------ start screen */
function renderModes() {
  const box = $('#modes'); box.replaceChildren();
  for (const m of MODES) {
    const input = h('input', { type: 'radio', name: 'mode', value: m, checked: m === S.mode, onchange: () => { S.mode = m; renderModes(); } });
    box.append(h('label', { class: 'mode' + (m === S.mode ? ' sel' : '') }, input,
      h('b', {}, t('mode_' + m), m === 'premium' ? h('span', { class: 'pill' }, t('default')) : null), h('p', {}, t('mode_' + m + '_d'))));
  }
}
function fillModeSelect(sel, value) {
  const cur = value || sel.value || S.mode; sel.replaceChildren();
  for (const m of MODES) sel.append(h('option', { value: m, selected: m === cur }, t('mode_' + m)));
}
function renderLimits() {
  if (S.cfg) $('#limits').textContent = t('limits', { files: S.cfg.max_files, mb: S.cfg.max_job_mb, fmb: S.cfg.max_file_mb });
}
function renderOldJobs() {
  const jobs = (S.oldJobs || []).filter((j) => !S.job || j.id !== S.job.id);
  const box = $('#old-jobs'); box.classList.toggle('hidden', !jobs.length);
  const ul = $('#old-jobs-list'); ul.replaceChildren();
  for (const j of jobs) {
    ul.append(h('li', {}, h('span', {}, t('photos_n', { n: j.counts.total }), ' · ', t('min_left', { m: Math.max(1, Math.ceil(j.expires_in / 60)) })),
      h('span', { class: 'row' },
        h('button', { class: 'btn sm', type: 'button', onclick: () => openJob(j.id) }, t('open')),
        h('button', { class: 'btn sm danger-o', type: 'button', onclick: () => removeJob(j.id) }, t('delete_job')))));
  }
}
async function showStart() {
  S.job = null; S.rev = 0; stopPolling();
  $('#sec-job').classList.add('hidden'); $('#sec-start').classList.remove('hidden');
  try { S.oldJobs = (await api('/jobs')).jobs; } catch { /* ignore */ }
  renderOldJobs();
}
async function openJob(id) {
  try { S.job = await api('/jobs/' + id); } catch (e) { toast(errText(e), true); return showStart(); }
  S.rev = S.job.rev; S.sig = ''; S.clickedZip = false;
  $('#sec-start').classList.add('hidden'); $('#sec-job').classList.remove('hidden');
  renderJob(); startPolling();
}
async function removeJob(id) {
  if (!confirm(t('confirm_delete'))) return;
  try { await api('/jobs/' + id, { method: 'DELETE' }); toast(t('deleted')); } catch (e) { if (e.code !== 'job_not_found') toast(errText(e), true); }
  if (S.job && S.job.id === id) { closeModal(); await showStart(); } else { S.oldJobs = (S.oldJobs || []).filter((j) => j.id !== id); renderOldJobs(); }
}

/* ------------------------------------------------------------------ picking files */
const drop = $('#drop');
$('#pick-photos').onclick = () => $('#in-photos').click();
$('#pick-folder').onclick = () => $('#in-folder').click();
$('#pick-zip').onclick = () => $('#in-zip').click();
$('#btn-new').onclick = () => $('#in-photos').click();
drop.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('#in-photos').click(); } });
for (const id of ['in-photos', 'in-folder', 'in-zip']) {
  $('#' + id).addEventListener('change', (e) => {
    const files = [...e.target.files];
    addFiles(files.map((f) => ({ file: f, path: f.webkitRelativePath || f.name }))); e.target.value = '';
  });
}
for (const ev of ['dragenter', 'dragover']) window.addEventListener(ev, (e) => { if (hasFiles(e)) { e.preventDefault(); drop.classList.add('over'); } });
for (const ev of ['dragleave', 'dragend']) window.addEventListener(ev, (e) => { if (e.target === document.documentElement || e.target === drop) drop.classList.remove('over'); });
window.addEventListener('drop', async (e) => {
  if (!hasFiles(e)) return; e.preventDefault(); drop.classList.remove('over');
  if ($('#view-app').classList.contains('hidden')) return;
  const dt = e.dataTransfer;
  const entries = [...dt.items].filter((i) => i.kind === 'file').map((i) => (i.webkitGetAsEntry ? i.webkitGetAsEntry() : null)); // must be read synchronously
  const plain = [...dt.files];
  const out = [];
  try {
    if (entries.some(Boolean)) { for (const en of entries) if (en) await walk(en, '', out); }
    else plain.forEach((f) => out.push({ file: f, path: f.name }));
  } catch { toast(t('err_generic'), true); }
  addFiles(out);
});
const hasFiles = (e) => e.dataTransfer && [...(e.dataTransfer.types || [])].includes('Files');
async function walk(entry, prefix, out) {
  if (entry.isFile) {
    const file = await new Promise((res, rej) => entry.file(res, rej));
    out.push({ file, path: prefix + entry.name });
  } else if (entry.isDirectory) {
    const reader = entry.createReader(); let batch;
    do {
      batch = await new Promise((res, rej) => reader.readEntries(res, rej));
      for (const e of batch) await walk(e, prefix + entry.name + '/', out);
    } while (batch.length);
  }
}

/* ------------------------------------------------------------------ uploading */
async function addFiles(list) {
  const jobMax = S.cfg.max_file_mb * 1e6, zipMax = S.cfg.max_zip_mb * 1e6;
  const todo = []; let skipped = 0;
  for (const it of list) {
    const path = it.path.replace(/\\/g, '/');
    const ext = extOf(path);
    if (isJunk(path)) continue;
    if (ext !== '.zip' && !ALLOWED.has(ext)) { skipped++; continue; }
    if (it.file.size > (ext === '.zip' ? zipMax : jobMax)) { toast(t('too_big', { name: it.file.name, mb: Math.round((ext === '.zip' ? zipMax : jobMax) / 1e6) }), true); continue; }
    if (it.file.size === 0) { skipped++; continue; }
    todo.push({ file: it.file, path });
  }
  S.clientIgnored += skipped;
  if (!todo.length) { if (skipped) renderJob(); return; }
  if (!S.job) {
    try { S.job = await api('/jobs', { method: 'POST', body: { mode: S.mode } }); } catch (e) { toast(errText(e), true); return; }
    S.rev = S.job.rev; S.sig = ''; S.clientIgnored = skipped;
    $('#sec-start').classList.add('hidden'); $('#sec-job').classList.remove('hidden'); startPolling();
  }
  if (!S.up) S.up = { total: 0, done: 0, failed: [], queue: [], active: 0, bytes: 0, sent: 0 };
  for (const x of todo) { S.up.queue.push(x); S.up.total++; S.up.bytes += x.file.size; }
  renderJob(); pump();
}
function pump() {
  const U = S.up; if (!U) return;
  while (U.active < 3 && U.queue.length) {
    const x = U.queue.shift(); U.active++;
    sendFile(x).catch((e) => U.failed.push({ path: x.path, e })).finally(() => {
      U.active--; U.done++; U.sent += x.file.size; renderUploadProgress();
      if (!U.queue.length && !U.active) finishUploads(); else pump();
    });
  }
  renderUploadProgress();
}
async function sendFile(x) {
  let last;
  for (let attempt = 0; attempt < 3; attempt++) {
    try { return await xhrUpload('/api/jobs/' + S.job.id + '/files?path=' + encodeURIComponent(x.path), x.file); }
    catch (e) { last = e; if (e.code !== 'network' || !S.job) break; await new Promise((r) => setTimeout(r, 800 * (attempt + 1))); }
  }
  throw last;
}
function xhrUpload(url, file) {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest(); x.open('POST', url);
    x.setRequestHeader('X-Requested-With', 'roomlit'); x.setRequestHeader('Content-Type', 'application/octet-stream');
    x.onload = () => {
      let d = null; try { d = JSON.parse(x.responseText); } catch { /* */ }
      if (x.status >= 200 && x.status < 300) resolve(d);
      else if (x.status === 401) { showLogin(); reject(new ApiError(401, 'unauthorized', '')); }
      else reject(new ApiError(x.status, d && d.error, d && d.message, d));
    };
    x.onerror = () => reject(new ApiError(0, 'network', t('err_network')));
    x.send(file);
  });
}
function finishUploads() {
  const U = S.up; S.up = null;
  if (U.failed.length) {
    const why = [...new Set(U.failed.map((f) => errText(f.e)))].join(' / ');
    toast(t('upload_failed', { n: U.failed.length, why }), true);
  }
  $('#upload-progress').classList.add('hidden'); poll(true); renderJob();
}
function renderUploadProgress() {
  const U = S.up, box = $('#upload-progress'); if (!U) return box.classList.add('hidden');
  box.classList.remove('hidden');
  $('#ubar').style.width = Math.min(100, Math.round((100 * U.sent) / Math.max(1, U.bytes))) + '%';
  $('#uprogress-text').textContent = t('uploading', { done: U.done, total: U.total });
}

/* ------------------------------------------------------------------ polling */
function startPolling() { stopPolling(); const tick = async () => { await poll(); S.timer = setTimeout(tick, pollDelay()); }; S.timer = setTimeout(tick, 800); }
function stopPolling() { if (S.timer) clearTimeout(S.timer); S.timer = null; }
const pollDelay = () => (S.up || (S.job && ['preparing', 'processing', 'organizing'].includes(S.job.phase))) ? 900 : 4000;
async function poll(force) {
  if (!S.job) return;
  try {
    const d = await api('/jobs/' + S.job.id + (force ? '' : '?since=' + S.rev));
    if (d.unchanged) { S.job.expires_in = d.expires_in; renderExpiry(); }
    else { S.job = d; S.rev = d.rev; renderJob(); }
  } catch (e) {
    if (e.code === 'job_not_found') { closeModal(); toast(t('err_job_not_found'), true); await showStart(); }
  }
}

/* ------------------------------------------------------------------ job view */
function renderExpiry() {
  const m = Math.max(1, Math.ceil((S.job ? S.job.expires_in : 0) / 60));
  const el = $('#retention'); if (el) el.textContent = t('retention', { m });
}
function renderJob() {
  const j = S.job; if (!j) return;
  const c = j.counts, working = c.queued + c.processing, prep = c.uploaded + c.analyzing, org = j.phase === 'organizing';
  $('#job-heading').textContent = j.roots.length === 1 ? j.roots[0] : t('job_heading', { n: c.total });
  $('#job-counts').replaceChildren(...[h('span', {}, t('c_original', { n: c.total })), h('span', { class: 'c-final' }, t('c_final', { n: c.final })),
    c.excluded ? h('span', { class: 'c-ex' }, t('c_excluded', { n: c.excluded })) : null, c.failed ? h('span', { class: 'c-bad' }, t('c_failed', { n: c.failed })) : null].filter(Boolean));
  $('#job-sub').replaceChildren(h('span', { id: 'retention' })); renderExpiry();

  const bStart = $('#btn-start'), toStart = c.to_start;
  bStart.classList.toggle('hidden', !(toStart > 0 && !working && !org));
  bStart.textContent = toStart === 1 ? t('start_one') : t('start', { n: toStart });
  bStart.disabled = !!S.up;
  const sm = $('#smart-row'); sm.classList.toggle('hidden', !(toStart > 0 && !working && !org)); $('#smart').checked = S.smart;
  const zip = $('#btn-zip'), canZip = c.done > 0, num = S.numbering ? 1 : 0;
  zip.classList.toggle('hidden', !canZip); zip.href = '/api/jobs/' + j.id + '/download.zip?numbering=' + num; zip.textContent = t('dl_zip', { name: j.zip_name });
  zip.setAttribute('aria-disabled', working || org ? 'true' : 'false');
  const lg = $('#btn-log'); lg.classList.toggle('hidden', !canZip); lg.href = '/api/jobs/' + j.id + '/log.csv?numbering=' + num;
  $('#numbering-row').classList.toggle('hidden', !canZip); $('#numbering').checked = S.numbering;

  const pg = $('#progress'), bar = $('#bar'); bar.classList.toggle('indet', org);
  if (org) { pg.classList.remove('hidden'); $('#progress-text').textContent = t('organizing'); }
  else if (working) {
    const total = c.done + c.failed + c.queued + c.processing;
    pg.classList.remove('hidden'); bar.style.width = Math.round((100 * (c.done + c.failed)) / Math.max(1, total)) + '%';
    $('#progress-text').textContent = t('processing', { done: c.done + c.failed, total });
  } else if (prep) {
    pg.classList.remove('hidden'); bar.style.width = Math.round((100 * (c.total - prep)) / Math.max(1, c.total)) + '%';
    $('#progress-text').textContent = t('preparing', { n: prep });
  } else if (c.done && !toStart) { pg.classList.remove('hidden'); bar.style.width = '100%'; $('#progress-text').textContent = t('all_done'); }
  else pg.classList.add('hidden');

  $('#banner-dl').classList.toggle('hidden', !(j.downloaded || S.clickedZip));
  $('#reedit').classList.toggle('hidden', !(c.done > 0 && !working && !org));
  const notes = $('#notes'); notes.replaceChildren();
  const ign = j.ignored_total + S.clientIgnored;
  if (ign) notes.append(h('div', { class: 'note' }, t('ignored', { n: ign })));
  if (j.already) notes.append(h('div', { class: 'note' }, t('already_n', { n: j.already })));
  if (c.renamed) notes.append(h('div', { class: 'note warn' }, t('renamed_n', { n: c.renamed })));
  if (c.failed) notes.append(h('div', { class: 'note bad' }, t('failed_n', { n: c.failed })));
  if (j.smart && j.ml === false && j.sets.some((x) => x.organized)) notes.append(h('div', { class: 'note warn' }, t('ml_off')));
  renderSets(j);
  if (S.modalId != null) renderModal();
}

const STATUS_CLASS = { done: 'ok', failed: 'bad', processing: 'work', queued: 'work', analyzing: 'work', uploaded: '', ready: '' };
const itemById = (id) => S.job && S.job.items.find((i) => i.id === id);

/* ---- cards */
function makeCard(it) {
  const img = h('img', { alt: '', loading: 'lazy', decoding: 'async' });
  const num = h('span', { class: 'num' }), ribbon = h('span', { class: 'ribbon' });
  const thumb = h('div', { class: 'thumb' }, img, num, ribbon);
  const name = h('div', { class: 'pname' }), chip = h('span', { class: 'chip' }), sim = h('span', { class: 'chip' }), why = h('div', { class: 'why' });
  const room = h('select', { class: 'room', 'aria-label': t('room_label') });
  room.addEventListener('change', () => act('/items/' + it.id + '/room', { room: room.value }));
  const mk = (cls, label, fn, text) => h('button', { type: 'button', class: 'mini ' + cls, title: label, 'aria-label': label, onclick: fn }, text);
  const bMain = mk('main', t('make_main'), () => act('/items/' + it.id + '/main'), '★ ' + t('make_main_s'));
  const bPrev = mk('mv', t('earlier'), () => shiftItem(it.id, -1), h('span', {}, '‹'));
  const bNext = mk('mv', t('later'), () => shiftItem(it.id, 1), h('span', {}, '›'));
  const bEx = mk('ex', t('exclude'), () => act('/items/' + it.id + '/exclude'), '✕');
  const bRe = mk('restore', t('restore'), () => act('/items/' + it.id + '/restore'), '↺ ' + t('restore'));
  const acts = h('div', { class: 'acts' }, bMain, bPrev, bNext, bEx, bRe);
  const el = h('div', { class: 'pcard', 'data-id': it.id }, h('button', { class: 'thumbbtn', type: 'button', onclick: () => openModal(it.id), 'aria-label': it.name }, thumb),
    h('div', { class: 'pinfo' }, name, h('div', { class: 'chips' }, chip, sim), room, why, acts));
  el.addEventListener('dragstart', (e) => { const x = itemById(it.id); if (!x || x.pos === 0) { e.preventDefault(); return; } S.drag = { id: it.id, set: x.set }; el.classList.add('dragging'); e.dataTransfer.effectAllowed = 'move'; try { e.dataTransfer.setData('text/plain', String(it.id)); } catch { /* */ } });
  el.addEventListener('dragend', () => { el.classList.remove('dragging'); clearIns(); S.drag = null; });
  return { el, img, num, ribbon, thumb, name, chip, sim, why, room, bMain, bPrev, bNext, bEx, bRe, key: null, roomsKey: null };
}
function updateCard(c, it, kind, idx, total) {
  const j = S.job;
  c.el.draggable = kind === 'arranged'; c.el.dataset.kind = kind;
  c.el.classList.toggle('main', kind === 'arranged' && idx === 0);
  c.name.textContent = it.name; c.name.title = it.name;
  c.num.classList.toggle('hidden', kind !== 'arranged'); c.num.textContent = idx + 1;
  c.ribbon.classList.toggle('hidden', !(kind === 'arranged' && idx === 0)); c.ribbon.textContent = '★ ' + t('main_photo');
  let label = t('s_' + it.status) + (it.status === 'done' && it.mode ? ' · ' + t('mode_' + it.mode) : '');
  if (it.status === 'failed') label = t('s_failed') + (it.err ? ': ' + it.err : '');
  c.chip.className = 'chip ' + (kind === 'excluded' ? '' : (STATUS_CLASS[it.status] || '')); c.chip.textContent = kind === 'excluded' ? '' : label;
  c.chip.classList.toggle('hidden', kind === 'excluded'); if (it.err) c.chip.title = it.err;
  const simmed = kind === 'arranged' && it.similar && it.similar.length;
  c.sim.className = 'chip work'; c.sim.textContent = t('similar'); c.sim.classList.toggle('hidden', !simmed);
  // room type: a suggestion unless the model was sure or the user chose it
  const showRoom = kind === 'arranged';
  c.room.classList.toggle('hidden', !showRoom);
  if (showRoom) {
    const key = j.rooms.join(',') + lang;
    if (c.roomsKey !== key) { c.room.replaceChildren(...j.rooms.map((r) => h('option', { value: r }, t('room_' + r)))); c.roomsKey = key; }
    c.room.value = it.room || 'other';
    const unsure = !it.room_sure && !it.room_user;
    c.room.classList.toggle('unsure', unsure); c.room.title = unsure ? t('suggested_room') : t('room_label');
  }
  const why = kind === 'excluded' ? (it.ex_why === 'dup' ? t('ex_dup', { name: (itemById(it.dup_of) || {}).name || '' }) : t('ex_user'))
    : (it.renamed ? t('renamed_hint', { name: it.out.split('/').pop() }) : '');
  c.why.textContent = why; c.why.classList.toggle('hidden', !why);
  c.bMain.classList.toggle('hidden', !(kind === 'arranged' && idx > 0));
  c.bPrev.classList.toggle('hidden', !(kind === 'arranged' && idx > 0)); c.bNext.classList.toggle('hidden', !(kind === 'arranged' && idx < total - 1));
  c.bEx.classList.toggle('hidden', kind !== 'arranged'); c.bRe.classList.toggle('hidden', kind !== 'excluded');
  c.thumb.classList.toggle('busy', ['processing', 'analyzing', 'queued'].includes(it.status) && kind !== 'excluded');
  const has = !['uploaded', 'analyzing'].includes(it.status) && !(it.status === 'failed' && !it.w);
  const key = has ? it.v + ':' + (it.status === 'done' ? 'a' : 'b') : null;
  if (key !== c.key) { c.key = key; if (key) c.img.src = '/api/jobs/' + j.id + '/items/' + it.id + '/preview/thumb?v=' + key; else c.img.removeAttribute('src'); }
}

/* ---- sets */
function renderSets(j) {
  const box = $('#sets');
  const bySet = new Map(j.sets.map((s) => [s.id, []]));
  for (const it of j.items) bySet.get(it.set).push(it);
  const sig = lang + '|' + j.sets.map((s) => `${s.id}:${s.organized ? 1 : 0}:${s.manual ? 1 : 0}`).join(',') + '#' + j.items.map((i) => `${i.id}.${i.set}.${i.pos}.${i.ex ? 1 : 0}`).join(',') + '#' + (S.openEx ? JSON.stringify(S.openEx) : '');
  const live = new Set(j.items.map((i) => i.id));
  for (const id of [...S.cards.keys()]) if (!live.has(id)) S.cards.delete(id);
  const card = (it) => { let c = S.cards.get(it.id); if (!c) { c = makeCard(it); S.cards.set(it.id, c); } return c; };
  const plan = [];                                    // [item, kind, index, total] for in-place updates
  if (sig !== S.sig) {
    S.sig = sig; box.replaceChildren();
    for (const s of j.sets) {
      const items = bySet.get(s.id);
      const arranged = items.filter((i) => i.pos > 0).sort((a, b) => a.pos - b.pos);
      const excluded = items.filter((i) => i.ex);
      const pending = items.filter((i) => i.pos === 0 && !i.ex);
      const sec = h('section', { class: 'setbox' });
      const root = j.roots.length > 1 ? s.key.split('/')[0] : null;
      const head = h('div', { class: 'sethead' }, h('h3', {}, s.label, root ? h('small', {}, root) : null,
        s.organized ? h('span', { class: 'chip' }, t('c_final', { n: arranged.length })) : null, s.manual ? h('span', { class: 'chip work' }, t('arranged_by_you')) : null));
      if (s.organized && arranged.length) head.append(h('button', { class: 'btn sm', type: 'button', onclick: () => act('/sets/' + s.id + '/reset-order') }, t(j.smart ? 'reset_order' : 'reset_order_plain')));
      sec.append(head);
      if (arranged.length) {
        sec.append(h('p', { class: 'hint' }, t('drag_hint')));
        const grid = h('div', { class: 'cards arranged', 'data-set': s.id });
        bindDrop(grid, s.id);
        arranged.forEach((it, n) => { grid.append(card(it).el); });
        sec.append(grid);
      }
      if (pending.length) {
        if (arranged.length) sec.append(h('p', { class: 'hint' }, t('pending_new')));
        const grid = h('div', { class: 'cards' }); pending.forEach((it) => grid.append(card(it).el)); sec.append(grid);
      }
      if (excluded.length) {
        const d = h('details', { class: 'excl' }, h('summary', {}, t('excluded_title', { n: excluded.length })));
        d.open = S.openEx[s.id] !== false;
        d.addEventListener('toggle', () => { S.openEx[s.id] = d.open; });
        const grid = h('div', { class: 'cards' }); excluded.forEach((it) => grid.append(card(it).el)); d.append(grid); sec.append(d);
      }
      box.append(sec);
    }
  }
  for (const s of j.sets) {
    const items = bySet.get(s.id);
    const arranged = items.filter((i) => i.pos > 0).sort((a, b) => a.pos - b.pos);
    arranged.forEach((it, n) => plan.push([it, 'arranged', n, arranged.length]));
    items.filter((i) => i.ex).forEach((it, n) => plan.push([it, 'excluded', n, 0]));
    items.filter((i) => i.pos === 0 && !i.ex).forEach((it, n) => plan.push([it, 'plain', n, 0]));
  }
  for (const [it, kind, n, total] of plan) { const c = S.cards.get(it.id); if (c) updateCard(c, it, kind, n, total); }
}

/* ---- ordering: drag and drop + buttons */
function setOrder(setId) { const s = S.job.sets.find((x) => x.id === setId); return s ? [...s.order] : []; }
function clearIns() { document.querySelectorAll('.ins-before,.ins-after').forEach((e) => e.classList.remove('ins-before', 'ins-after')); }
function dropSpot(grid, e) {
  const cards = [...grid.querySelectorAll('.pcard[data-kind="arranged"]')].filter((c) => +c.dataset.id !== S.drag.id);
  if (!cards.length) return null;
  let best = null, bd = Infinity;
  for (const c of cards) { const r = c.getBoundingClientRect(), dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height / 2), d = dx * dx + 4 * dy * dy; if (d < bd) { bd = d; best = { c, r, dx }; } }
  const rtl = document.documentElement.dir === 'rtl';
  const before = rtl ? best.dx > 0 : best.dx < 0;
  return { card: best.c, before, cards };
}
function bindDrop(grid, setId) {
  grid.addEventListener('dragover', (e) => { if (!S.drag || S.drag.set !== setId) return; e.preventDefault(); e.dataTransfer.dropEffect = 'move'; clearIns(); const sp = dropSpot(grid, e); if (sp) sp.card.classList.add(sp.before ? 'ins-before' : 'ins-after'); });
  grid.addEventListener('dragleave', (e) => { if (!grid.contains(e.relatedTarget)) clearIns(); });
  grid.addEventListener('drop', (e) => {
    if (!S.drag || S.drag.set !== setId) return; e.preventDefault(); clearIns();
    const sp = dropSpot(grid, e); if (!sp) return;
    const ids = sp.cards.map((c) => +c.dataset.id); const at = ids.indexOf(+sp.card.dataset.id) + (sp.before ? 0 : 1);
    ids.splice(at, 0, S.drag.id); reorder(setId, ids);
  });
}
async function reorder(setId, ids) {
  const s = S.job.sets.find((x) => x.id === setId); if (!s) return;
  if (ids.join() === s.order.join()) return;
  s.order = ids; s.manual = true;                                            // show it at once, confirm with the server below
  ids.forEach((id, n) => { const it = itemById(id); if (it) it.pos = n + 1; });
  renderJob();
  try { await api('/jobs/' + S.job.id + '/sets/' + setId + '/order', { method: 'POST', body: { order: ids } }); } catch (e) { toast(errText(e), true); }
  await poll(true);
}
function shiftItem(id, d) {
  const it = itemById(id); if (!it) return;
  const ids = setOrder(it.set), i = ids.indexOf(id), k = i + d; if (i < 0 || k < 0 || k >= ids.length) return;
  ids.splice(i, 1); ids.splice(k, 0, id); reorder(it.set, ids);
}
async function act(path, body) {
  try { await api('/jobs/' + S.job.id + path, { method: 'POST', body: body || {} }); } catch (e) { toast(errText(e), true); }
  await poll(true);
}

/* ------------------------------------------------------------------ job actions */
$('#btn-start').addEventListener('click', async () => {
  try { await api('/jobs/' + S.job.id + '/start', { method: 'POST', body: { mode: S.mode, smart: S.smart } }); await poll(true); } catch (e) { toast(errText(e), true); }
});
$('#btn-zip').addEventListener('click', (e) => { if ($('#btn-zip').getAttribute('aria-disabled') === 'true') { e.preventDefault(); return; } S.clickedZip = true; setTimeout(() => $('#banner-dl').classList.remove('hidden'), 600); });
$('#numbering').addEventListener('change', (e) => { S.numbering = e.target.checked; try { localStorage.setItem('rl_num2', S.numbering ? '1' : '0'); } catch { /* */ } renderJob(); });
$('#smart').addEventListener('change', (e) => { S.smart = e.target.checked; try { localStorage.setItem('rl_smart', S.smart ? '1' : '0'); } catch { /* */ } });
$('#btn-delete').addEventListener('click', () => removeJob(S.job.id));
$('#btn-delete-now').addEventListener('click', () => removeJob(S.job.id));
$('#btn-reedit-all').addEventListener('click', async () => {
  try { await api('/jobs/' + S.job.id + '/reprocess', { method: 'POST', body: { mode: $('#reedit-mode').value } }); toast(t('reprocess_queued')); await poll(true); } catch (e) { toast(errText(e), true); }
});

/* ------------------------------------------------------------------ compare modal */
const modal = $('#modal'), cmp = $('#cmp');
function orderedIds() { return S.job ? S.job.items.map((i) => i.id) : []; }
function openModal(id) { S.modalId = id; modal.classList.remove('hidden'); document.body.style.overflow = 'hidden'; S.mKey = null; renderModal(); $('#m-close').focus(); }
function closeModal() { S.modalId = null; modal.classList.add('hidden'); document.body.style.overflow = ''; }
function step(d) { const ids = orderedIds(); const i = ids.indexOf(S.modalId); if (i < 0) return; S.modalId = ids[(i + d + ids.length) % ids.length]; S.mKey = null; renderModal(); }
$('#m-close').onclick = closeModal; $('#m-prev').onclick = () => step(-1); $('#m-next').onclick = () => step(1);
modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
window.addEventListener('keydown', (e) => {
  if (S.modalId == null) return;
  if (e.key === 'Escape') closeModal(); else if (e.key === 'ArrowRight' && e.target.id !== 'cmp-handle') step(lang === 'ar' ? -1 : 1); else if (e.key === 'ArrowLeft' && e.target.id !== 'cmp-handle') step(lang === 'ar' ? 1 : -1);
});
function renderModal() {
  const it = itemById(S.modalId); if (!it) return closeModal();
  $('#m-name').textContent = it.name;
  const pos = it.pos ? '#' + it.pos + ' · ' : '';
  $('#m-meta').textContent = pos + (it.w ? it.w + '×' + it.h + ' · ' : '') + t('s_' + it.status) + (it.err ? ': ' + it.err : '') + (it.room ? ' · ' + t('room_' + it.room) : '') + (it.status === 'done' ? ' · ' + t('outpath') + ' ' + it.out : '');
  const base = '/api/jobs/' + S.job.id + '/items/' + it.id + '/preview/';
  const done = it.status === 'done';
  const key = it.id + ':' + it.v + ':' + done + ':' + (['uploaded', 'analyzing'].includes(it.status));
  if (key !== S.mKey) {
    S.mKey = key;
    const ready = !['uploaded', 'analyzing'].includes(it.status);
    $('#cmp-before').src = ready ? base + 'before?v=' + it.id : ''; $('#cmp-after').src = done ? base + 'after?v=' + it.v : (ready ? base + 'before?v=' + it.id : '');
    $('#tag-after').classList.toggle('hidden', !done); $('#tag-before').classList.toggle('hidden', !done);
    cmp.querySelector('.cmp-clip').classList.toggle('hidden', !done); $('#cmp-handle').classList.toggle('hidden', !done);
    const p = $('#m-pending'); p.classList.toggle('hidden', done || it.status === 'failed'); p.textContent = it.ex ? t('compare_excluded') : t('compare_pending');
    setPos(50);
  }
  const busy = ['queued', 'processing', 'uploaded', 'analyzing'].includes(it.status);
  fillModeSelect($('#m-mode'), $('#m-mode').dataset.id == it.id ? $('#m-mode').value : (it.mode || S.job.mode)); $('#m-mode').dataset.id = it.id;
  $('#m-reedit').disabled = busy || it.status === 'ready';
  $('#m-main').classList.toggle('hidden', !(it.pos > 1)); $('#m-excl').classList.toggle('hidden', it.status === 'failed');
  $('#m-excl').textContent = it.ex ? t('restore') : t('exclude');
  const dl = $('#m-dl'); dl.classList.toggle('hidden', !done); dl.href = '/api/jobs/' + S.job.id + '/items/' + it.id + '/download';
}
$('#m-main').addEventListener('click', () => act('/items/' + S.modalId + '/main'));
$('#m-excl').addEventListener('click', () => { const it = itemById(S.modalId); if (it) act('/items/' + it.id + (it.ex ? '/restore' : '/exclude')); });
$('#cmp-after').addEventListener('load', (e) => { const i = e.target; if (i.naturalWidth) { cmp.style.aspectRatio = i.naturalWidth + ' / ' + i.naturalHeight; fitCmp(i); } });
$('#cmp-before').addEventListener('load', (e) => { const i = e.target; const it = itemById(S.modalId); if (i.naturalWidth && !(it && it.status === 'done')) { cmp.style.aspectRatio = i.naturalWidth + ' / ' + i.naturalHeight; fitCmp(i); } });
function fitCmp(i) { // keep the stage inside the viewport while preserving the photo's aspect ratio
  const maxH = Math.max(240, window.innerHeight - 260); cmp.style.width = Math.min(cmp.parentElement.clientWidth - 0, maxH * (i.naturalWidth / i.naturalHeight)) + 'px';
}
window.addEventListener('resize', () => { const i = $('#cmp-after'); if (S.modalId != null && i.naturalWidth) fitCmp(i); });
function setPos(p) { p = Math.max(0, Math.min(100, p)); cmp.style.setProperty('--pos', p + '%'); $('#cmp-handle').setAttribute('aria-valuenow', Math.round(p)); }
(() => {
  let drag = false;
  const move = (e) => { const r = cmp.getBoundingClientRect(); setPos(((e.clientX - r.left) / r.width) * 100); };
  cmp.addEventListener('pointerdown', (e) => { drag = true; cmp.setPointerCapture(e.pointerId); move(e); });
  cmp.addEventListener('pointermove', (e) => { if (drag) move(e); });
  cmp.addEventListener('pointerup', () => { drag = false; }); cmp.addEventListener('pointercancel', () => { drag = false; });
  $('#cmp-handle').addEventListener('keydown', (e) => {
    const cur = parseFloat(getComputedStyle(cmp).getPropertyValue('--pos')) || 50;
    if (e.key === 'ArrowLeft') { setPos(cur - 5); e.preventDefault(); e.stopPropagation(); } if (e.key === 'ArrowRight') { setPos(cur + 5); e.preventDefault(); e.stopPropagation(); }
  });
})();
$('#m-reedit').addEventListener('click', async () => {
  try { await api('/jobs/' + S.job.id + '/items/' + S.modalId + '/reprocess', { method: 'POST', body: { mode: $('#m-mode').value } }); toast(t('reprocess_queued')); await poll(true); } catch (e) { toast(errText(e), true); }
});

/* ------------------------------------------------------------------ boot */
(async function boot() {
  applyLang();
  try { await api('/me'); await showApp(); } catch (e) { if (e.status !== 401) { showLogin(); } }
})();
})();
