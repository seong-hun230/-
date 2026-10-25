/**
 * 2본 2팀 워킹순번표 — Google Apps Script 서버 코드
 *
 * 구글 시트에 붙여서 쓰는 코드입니다.
 * - '순번' 시트 : 담당자 순서 (위에서부터). 이름을 바꾸거나 추가하면 바로 반영됩니다.
 * - '기록' 시트 : 워킹 받은 기록 (일시, 담당자). 자동으로 쌓입니다.
 */

const TEAM_NAME = '2본 2팀';
const DEFAULT_STAFF = ['홍명숙 실장', '김기엽 부장', '서정주 부장'];
const TZ = 'Asia/Seoul';
const STAFF_SHEET = '순번';
const LOG_SHEET = '기록';
const MAX_ENTRIES = 60; // 화면에 보여줄 최근 기록 수
const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];
const TYPE_RECEIVED = '받음';
const TYPE_SKIPPED = '건너뜀';

function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle(TEAM_NAME + ' 워킹순번표')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/** 현재 순번 상태 조회 */
function getState() {
  return buildState_();
}

/**
 * 워킹 받음 체크.
 * expectedName / expectedCount 는 화면에 보이던 상태입니다.
 * 그 사이 다른 직원이 먼저 체크했으면 기록하지 않고 최신 상태만 돌려줍니다.
 */
function checkWalking(expectedName, expectedCount) {
  return record_(TYPE_RECEIVED, expectedName, expectedCount);
}

/** 부재 시 건너뛰기: 받은 건수에는 넣지 않고 순번만 다음 사람으로 넘깁니다. */
function skipTurn(expectedName, expectedCount) {
  return record_(TYPE_SKIPPED, expectedName, expectedCount);
}

/** 마지막 기록 1건 취소 (잘못 눌렀을 때) */
function undoLast(expectedCount) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) throw new Error('사용자가 많습니다. 잠시 후 다시 눌러 주세요.');
  try {
    const before = buildState_();
    if (before.count !== expectedCount || before.count === 0) {
      before.ok = false;
      before.notice = before.count === 0
        ? '취소할 기록이 없습니다.'
        : '그 사이 새 기록이 생겨서 취소하지 않았습니다. 기록을 다시 확인해 주세요.';
      return before;
    }
    const sh = logSheet_();
    sh.deleteRow(sh.getLastRow());
    SpreadsheetApp.flush();
    const after = buildState_();
    after.ok = true;
    after.undone = before.entries[0] || null;
    return after;
  } finally {
    lock.releaseLock();
  }
}

/* ---------- 내부 함수 ---------- */

function record_(type, expectedName, expectedCount) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) throw new Error('사용자가 많습니다. 잠시 후 다시 눌러 주세요.');
  try {
    const before = buildState_();
    if (before.current !== expectedName || before.count !== expectedCount) {
      before.ok = false;
      before.notice = '그 사이 다른 직원이 먼저 체크해서 순번이 바뀌었습니다. 최신 순번으로 다시 확인해 주세요.';
      return before;
    }
    const now = new Date();
    const e = entry_(now, expectedName, type);
    logSheet_().appendRow([now, expectedName, e.dayLabel + ' ' + e.time, type]);
    SpreadsheetApp.flush();
    const after = buildState_();
    after.ok = true;
    after.checked = e;
    return after;
  } finally {
    lock.releaseLock();
  }
}

function buildState_() {
  const staffNames = getStaff_();
  const sh = logSheet_();
  const last = sh.getLastRow();
  const rows = last > 1 ? sh.getRange(2, 1, last - 1, 4).getValues() : [];
  const todayKey = Utilities.formatDate(new Date(), TZ, 'yyyy-MM-dd');

  const all = [];
  rows.forEach(function (r) {
    const d = r[0] instanceof Date ? r[0] : new Date(r[0]);
    const name = String(r[1] || '').trim();
    if (!name || isNaN(d.getTime())) return;
    all.push(entry_(d, name, String(r[3] || '').trim() || TYPE_RECEIVED));
  });

  const staff = staffNames.map(function (name) {
    const mine = all.filter(function (e) { return e.name === name && e.type === TYPE_RECEIVED; });
    const lastOne = mine.length ? mine[mine.length - 1] : null;
    return {
      name: name,
      total: mine.length,
      today: mine.filter(function (e) { return e.day === todayKey; }).length,
      lastLabel: lastOne ? lastOne.dayLabel + ' ' + lastOne.time : ''
    };
  });

  let currentIndex = 0;
  if (all.length) {
    const idx = staffNames.indexOf(all[all.length - 1].name);
    currentIndex = idx === -1 ? 0 : (idx + 1) % staffNames.length;
  }
  const nextIndex = (currentIndex + 1) % staffNames.length;

  let appUrl = '';
  try { appUrl = ScriptApp.getService().getUrl() || ''; } catch (err) { appUrl = ''; }

  return {
    team: TEAM_NAME,
    staff: staff,
    currentIndex: currentIndex,
    current: staffNames[currentIndex],
    next: staffNames[nextIndex],
    count: rows.length,
    todayLabel: dayLabel_(new Date()),
    entries: all.slice(-MAX_ENTRIES).reverse(),
    appUrl: appUrl,
    serverTime: Utilities.formatDate(new Date(), TZ, 'HH:mm:ss')
  };
}

function entry_(d, name, type) {
  return {
    name: name,
    type: type,
    ts: d.getTime(),
    day: Utilities.formatDate(d, TZ, 'yyyy-MM-dd'),
    dayLabel: dayLabel_(d),
    time: Utilities.formatDate(d, TZ, 'HH:mm')
  };
}

/** 예: 10월 25일(일) */
function dayLabel_(d) {
  const wd = WEEKDAYS[Number(Utilities.formatDate(d, TZ, 'u')) % 7];
  return Utilities.formatDate(d, TZ, 'M월 d일') + '(' + wd + ')';
}

function getStaff_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(STAFF_SHEET);
  if (!sh) {
    sh = ss.insertSheet(STAFF_SHEET);
    sh.getRange(1, 1).setValue('담당자 (위에서부터 순서대로, "이름 직급")');
    sh.getRange(2, 1, DEFAULT_STAFF.length, 1).setValues(DEFAULT_STAFF.map(function (n) { return [n]; }));
    sh.setColumnWidth(1, 320);
  }
  const last = sh.getLastRow();
  const names = last > 1
    ? sh.getRange(2, 1, last - 1, 1).getValues()
        .map(function (r) { return String(r[0] || '').trim(); })
        .filter(function (n) { return n; })
    : [];
  return names.length ? names : DEFAULT_STAFF.slice();
}

function logSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(LOG_SHEET);
  if (!sh) {
    sh = ss.insertSheet(LOG_SHEET);
    sh.getRange(1, 1, 1, 4).setValues([['일시', '담당자', '표시', '구분']]);
    sh.setFrozenRows(1);
    sh.setColumnWidth(1, 170);
    sh.setColumnWidth(2, 140);
    sh.setColumnWidth(3, 160);
  }
  if (!sh.getRange(1, 4).getValue()) sh.getRange(1, 4).setValue('구분');
  return sh;
}
