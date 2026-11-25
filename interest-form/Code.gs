/**
 * 대전 씨엘리오 스위첸 관심고객 등록 — 구글 시트 저장용 Apps Script
 *
 * 1) 구글 시트를 하나 만들고 [확장 프로그램] → [Apps Script]를 엽니다.
 * 2) 이 코드를 Code.gs 에 통째로 붙여 넣고, HTML 파일 'index'를 추가해 index.html 내용을 붙여 넣습니다.
 * 3) [배포] → [새 배포] → 유형: 웹 앱 / 실행: 나 / 액세스: 모든 사용자 → 배포
 *    나온 주소(…/exec)가 고객에게 보낼 등록 페이지 주소입니다.
 */

// ▼ 여기만 바꾸세요 ▼
var SETTINGS = {
  SHEET_NAME: '관심고객',               // 등록 내용이 쌓일 시트 탭 이름
  NOTIFY_EMAIL: '',                     // 새 등록 알림 받을 이메일 (비우면 알림 없음). 예: 'me@gmail.com'
  PAGE_TITLE: '대전 씨엘리오 스위첸 관심고객 등록'
};
// ▲ 여기까지 ▲

var HEADERS = ['등록일시', '이름', '연락처', '관심 상품', '구매 목적', '거주 지역', '상담 방법',
  '연락 희망 시간', '궁금한 점', '개인정보 동의', '마케팅 수신 동의', '유입 경로', '기기', '중복 여부', '상담 메모'];

/** 등록 페이지 보여주기 */
function doGet() {
  return HtmlService.createHtmlOutputFromFile('index')
    .setTitle(SETTINGS.PAGE_TITLE)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

/** 다른 사이트(넷리파이 등)에 올린 페이지에서 보낼 때 */
function doPost(e) {
  var data = {};
  try {
    data = JSON.parse(e.postData.contents);
  } catch (err) {
    data = (e && e.parameter) || {};
  }
  var result = saveLead(data);
  return ContentService.createTextOutput(JSON.stringify(result)).setMimeType(ContentService.MimeType.JSON);
}

/** 등록 내용을 검사하고 시트에 한 줄 추가한다 (페이지에서 google.script.run 으로도 호출) */
function saveLead(data) {
  data = data || {};
  // 스팸 방지: 숨긴 칸이 채워졌거나 2초 안에 제출된 경우 조용히 무시
  if (data.website || (data.elapsed !== undefined && Number(data.elapsed) < 2)) return { ok: true };

  var name = clean_(data.name, 20);
  var phone = String(data.phone || '').replace(/[^0-9]/g, '');
  if (name.length < 2) return { ok: false, error: '이름을 2자 이상 입력해 주세요.' };
  if (!/^01[016789][0-9]{7,8}$/.test(phone)) return { ok: false, error: '휴대폰 번호를 확인해 주세요.' };
  if (!clean_(data.interest, 100)) return { ok: false, error: '관심 상품을 선택해 주세요.' };
  if (data.privacy !== true && data.privacy !== 'true') return { ok: false, error: '개인정보 수집·이용에 동의해 주세요.' };

  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    var sheet = getSheet_();
    var phoneText = formatPhone_(phone);
    var duplicate = isDuplicate_(sheet, phoneText) ? '중복' : '';
    sheet.appendRow([
      new Date(),
      name,
      "'" + phoneText,                 // 앞의 0이 사라지지 않게 글자로 저장
      clean_(data.interest, 100),
      clean_(data.purpose, 20),
      clean_(data.region, 20),
      clean_(data.contact, 20),
      clean_(data.time, 20),
      clean_(data.message, 500),
      '동의',
      (data.marketing === true || data.marketing === 'true') ? '동의' : '미동의',
      clean_(data.source, 200),
      clean_(data.device, 10),
      duplicate,
      ''
    ]);
    notify_(name, phoneText, data, duplicate);
  } finally {
    lock.releaseLock();
  }
  return { ok: true };
}

function getSheet_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SETTINGS.SHEET_NAME) || ss.insertSheet(SETTINGS.SHEET_NAME);
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(HEADERS);
    sheet.getRange(1, 1, 1, HEADERS.length).setFontWeight('bold').setBackground('#13306b').setFontColor('#ffffff');
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function isDuplicate_(sheet, phoneText) {
  var last = sheet.getLastRow();
  if (last < 2) return false;
  var phones = sheet.getRange(2, 3, last - 1, 1).getValues();
  for (var i = 0; i < phones.length; i++) {
    if (String(phones[i][0]).replace(/^'/, '') === phoneText) return true;
  }
  return false;
}

/** 줄바꿈·공백 정리 + 시트 수식으로 실행되지 않게 막기 (=, +, -, @ 로 시작하면 앞에 ' 를 붙임) */
function clean_(value, max) {
  var s = String(value === undefined || value === null ? '' : value).replace(/[\r\n\t]+/g, ' ').trim().slice(0, max);
  return /^[=+\-@]/.test(s) ? "'" + s : s;
}

function formatPhone_(d) {
  return d.length === 11 ? d.slice(0, 3) + '-' + d.slice(3, 7) + '-' + d.slice(7)
    : d.slice(0, 3) + '-' + d.slice(3, 6) + '-' + d.slice(6);
}

function notify_(name, phoneText, data, duplicate) {
  if (!SETTINGS.NOTIFY_EMAIL) return;
  var body = [
    '새 관심고객이 등록되었습니다.' + (duplicate ? ' (이미 등록된 번호)' : ''),
    '',
    '이름: ' + name,
    '연락처: ' + phoneText,
    '관심 상품: ' + clean_(data.interest, 100),
    '구매 목적: ' + (clean_(data.purpose, 20) || '-'),
    '거주 지역: ' + (clean_(data.region, 20) || '-'),
    '상담 방법: ' + (clean_(data.contact, 20) || '-') + ' / ' + (clean_(data.time, 20) || '시간 무관'),
    '궁금한 점: ' + (clean_(data.message, 500) || '-'),
    '',
    '시트에서 전체 목록 보기: ' + SpreadsheetApp.getActiveSpreadsheet().getUrl()
  ].join('\n');
  MailApp.sendEmail(SETTINGS.NOTIFY_EMAIL, '[관심고객] ' + name + ' · ' + clean_(data.interest, 40), body);
}
