/* ============================================================================
   JAWL · Консоль агента — поведение

   ВСЕ точки соприкосновения с бэкендом собраны в объекте `api` ниже.
   Прототип работает на заглушках; при интеграции меняются только тела
   методов `api.*`, остальной код трогать не нужно.
   Карта интеграции: web/README.md
   ============================================================================ */

(function(){
  "use strict";


  /* ==========================================================================
     СЛОЙ ИНТЕГРАЦИИ

     Единственное место, где консоль обращается наружу. Сейчас все методы —
     заглушки: показывают тост и возвращают Promise.resolve(). При подключении
     бэкенда заменяются тела методов, вызывающий код не меняется.

     Каждый метод помечен: TODO(api) <метод> <предполагаемый маршрут>
     Подробности и открытые вопросы — в web/README.md.
     ========================================================================== */
  /* Токен из адреса страницы нужно повторять в запросах: EventSource не умеет
     задавать заголовки, а без токена сервер ответит 401. */
  var CONSOLE_TOKEN = new URLSearchParams(location.search).get("token") || "";

  function apiUrl(path, params){
    var query = new URLSearchParams(params || {});
    if (CONSOLE_TOKEN) query.set("token", CONSOLE_TOKEN);
    var tail = query.toString();
    return tail ? path + "?" + tail : path;
  }

  /* Ответ сервера может оказаться не JSON: старый процесс без нужного маршрута
     отдаёт "404: Not Found" простым текстом, и JSON.parse спотыкается на двоеточии.
     Разбираем это в понятное сообщение, а не в «Unexpected non-whitespace character». */
  function asJson(r){
    var type = r.headers.get("content-type") || "";
    if (type.indexOf("json") > -1) return r.json();
    return r.text().then(function(text){
      if (r.status === 404 || r.status === 405) {
        throw new Error("сервер не знает этот маршрут (" + r.status
          + "). Скорее всего запущена старая версия — перезапустите: python -m src.web");
      }
      throw new Error("сервер ответил не JSON (" + r.status + "): " + text.slice(0, 80));
    });
  }

  var api = {

    /* ---------- конфигурация ---------- */

    /* ПОДКЛЮЧЕНО. Отдаёт {values: {"источник:путь": значение}, lists: {id: [...]}}.
       Соответствие ключей — src/web/schema.py, тот же ключ стоит в data-cfg. */
    loadConfig: function(){
      return fetch(apiUrl("/api/config"), {headers: {"Accept": "application/json"}})
        .then(asJson);
    },

    /* ПОДКЛЮЧЕНО. Пишет settings.yaml построчно (комментарии и отступы целы)
       и .env точечной заменой. Ответ: {ok, written: [файлы], unknown, restartRequired}. */
    saveConfig: function(payload){
      return fetch(apiUrl("/api/config"), {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      }).then(asJson);
    },

    /* ---------- жизненный цикл агента ---------- */

    /* ПОДКЛЮЧЕНО. Поднимает src/main.py отдельным процессом. Ответ приходит
       через несколько секунд: сервер ждёт, не упал ли агент сразу. */
    startAgent: function(){
      return fetch(apiUrl("/api/agent/start"), {method: "POST"}).then(asJson);
    },

    /* ПОДКЛЮЧЕНО. Кладёт файл-сигнал agent.stop, который ловит сам фреймворк
       («[System] Received stop file signal»), и ждёт корректного завершения. */
    stopAgent: function(){
      return fetch(apiUrl("/api/agent/stop"), {method: "POST"}).then(asJson);
    },

    /* ПОДКЛЮЧЕНО. Реальное состояние процесса: работает ли, pid, время работы. */
    agentStatus: function(){
      return fetch(apiUrl("/api/agent/status")).then(asJson);
    },

    /* ПОДКЛЮЧЕНО. Состояние такта: сервер разбирает logs/main.log и повторяет
       расчёт следующего пробуждения из heartbeat.py. Своего состояния агент
       наружу не отдаёт — он в отдельном процессе. */
    tickState: function(){
      return fetch(apiUrl("/api/tick")).then(asJson);
    },

    /* ---------- логи ---------- */

    /* ПОДКЛЮЧЕНО. Хвост logs/main.log и смещение, с которого продолжать. */
    loadLogs: function(){
      return fetch(apiUrl("/api/logs")).then(asJson);
    },

    /* ПОДКЛЮЧЕНО. Дозапись через Server-Sent Events. Сервер шлёт только целые
       строки, поэтому запись не приедет разрезанной посередине. */
    subscribeLogs: function(offset, onChunk){
      var source = new EventSource(apiUrl("/api/logs/stream", {offset: offset}));
      source.onmessage = function(event){
        try { onChunk(JSON.parse(event.data)); } catch (e) { /* пропускаем мусор */ }
      };
      return function(){ source.close(); };
    },

    /* ПОДКЛЮЧЕНО. Отдаёт файл целиком. */
    downloadLogs: function(){
      window.location.href = apiUrl("/api/logs/download");
      return Promise.resolve();
    },

    /* ---------- чат ---------- */

    /* ПОДКЛЮЧЕНО. Переписка из history.json агента и состояние связи с его
       терминалом. История видна и при остановленном агенте — файл ведёт он. */
    loadChat: function(){
      return fetch(apiUrl("/api/chat")).then(asJson);
    },

    /* ПОДКЛЮЧЕНО. Уходит в терминальный канал агента и публикует
       HOST_TERMINAL_MESSAGE (CRITICAL) — то есть будит его немедленно. */
    sendMessage: function(text){
      return fetch(apiUrl("/api/chat"), {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({text: text})
      }).then(asJson);
    },

    /* ПОДКЛЮЧЕНО. Поток реплик агента. Пока поток открыт, консоль числится у
       агента открытым терминалом оператора — поэтому подписываемся только на
       время, пока вкладка «Чат» на экране. */
    subscribeChat: function(after, onData, onError){
      var stream = new EventSource(apiUrl("/api/chat/stream", {after: after || 0}));
      stream.onmessage = function(e){
        try { onData(JSON.parse(e.data)); } catch (err) { /* ping */ }
      };
      stream.onerror = function(){ if (onError) onError(); };
      return function(){ stream.close(); };
    },

    /* ПОДКЛЮЧЕНО. Мотиваторы из таблицы drives: дефицит вычисляется из времени
       последнего насыщения по формуле фреймворка. */
    loadDrives: function(){
      return fetch(apiUrl("/api/drives")).then(asJson);
    },

    /* ПОДКЛЮЧЕНО. Правит скорость и интервал у своих мотиваторов.
       Фундаментальные задаются в settings.yaml — их сюда не шлём. */
    saveDrives: function(updates){
      return fetch(apiUrl("/api/drives"), {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({updates: updates})
      }).then(asJson);
    },

    /* ---------- базы данных ---------- */

    /* ПОДКЛЮЧЕНО. Счётчики трёх баз и размеры каталогов. Читаются из самих
       хранилищ; лимиты сервер берёт из settings.yaml, чтобы «сколько из
       скольких» не расходилось с конфигом. */
    loadDbStats: function(){
      return fetch(apiUrl("/api/db/stats")).then(asJson);
    },

    /* ПОДКЛЮЧЕНО. Необратимая очистка выбранной области. Сервер откажет, пока
       агент запущен: он держит базы открытыми. */
    wipe: function(scope){
      return fetch(apiUrl("/api/db/wipe"), {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({scope: scope})
      }).then(asJson);
    },

    /* ПОДКЛЮЧЕНО. Открывает каталог в файловом менеджере ОС: для файла — папку,
       в которой он лежит. Работает, только когда консоль открыта на той же
       машине, где запущен сервер; на VPS кнопка бесполезна. */
    openDir: function(path){
      return fetch(apiUrl("/api/fs/open"), {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({path: path})
      }).then(asJson).then(function(res){
        if (!res.ok) toast("Не открылось: " + (res.error || "неизвестная ошибка"));
        return res;
      }).catch(function(err){ toast("Не открылось: " + err.message); });
    },

    /* ---------- файлы ---------- */

    /* TODO(api) GET /api/files/{id} и PUT /api/files/{id} — редактор содержимого.
       Пока кнопка «Открыть» показывает файл в проводнике через openDir. */
    openFile: function(path){
      return api.openDir(path);
    },

    /* ---------- интерфейсы ---------- */

    /* TODO(api) POST /api/interfaces/reload — перечитать плагины L2 без рестарта.
       Требует meta.access_level >= 2 (ARCHITECT), см. docs/yaml/interfaces/meta.md */
    reloadInterfaces: function(){
      toast("Прототип: плагины не перезагружаются");
      return Promise.resolve();
    },

    /* TODO(api) GET /api/interfaces/skills — {имя_интерфейса: число}
       Считается из _REGISTRY (src/l3_agent/skills/registry.py), имена навыков
       вида "HostOSReader.read_file" группируются по классу. */
    loadSkillCounts: function(){
      return Promise.resolve(null);
    },

    /* ---------- LLM ---------- */

    /* TODO(api) POST /api/llm/check — прогнать все ключи из пула.
       Ответ: [{index, status: "ok"|"cooldown"|"dead", detail}]
       В логах эти состояния уже есть: "Invalid API key (401). Removing from
       pool", "Key ... cooled down for 30 sec (Rate Limit)". */
    checkLlmKeys: function(){
      toast("Прототип: ключи не проверяются");
      return Promise.resolve([]);
    }
  };

  /* ---------- переключение вкладок ---------- */
  var tabs = document.querySelectorAll(".tab");
  var panels = document.querySelectorAll(".panel");
  tabs.forEach(function(t){
    t.addEventListener("click", function(){
      tabs.forEach(function(x){ x.setAttribute("aria-selected","false"); });
      t.setAttribute("aria-selected","true");
      panels.forEach(function(p){
        p.classList.toggle("panel-hidden", p.dataset.panel !== t.dataset.tab);
      });
    });
  });

  /* ---------- подвкладки ---------- */
  document.querySelectorAll(".seg").forEach(function(seg){
    var section = seg.closest(".panel");
    seg.querySelectorAll("button").forEach(function(b){
      b.addEventListener("click", function(){
        seg.querySelectorAll("button").forEach(function(x){ x.setAttribute("aria-selected","false"); });
        b.setAttribute("aria-selected","true");
        section.querySelectorAll(":scope > .scroll > .sub").forEach(function(s){
          s.classList.toggle("panel-hidden", s.dataset.sub !== b.dataset.sub);
        });
      });
    });
  });

  /* ---------- переключатели видов внутри вкладки ---------- */
  document.querySelectorAll("[data-viewgroup]").forEach(function(group){
    var scope = group.parentElement;
    group.querySelectorAll("[data-view]").forEach(function(b){
      b.addEventListener("click", function(){
        group.querySelectorAll("[data-view]").forEach(function(x){ x.setAttribute("aria-pressed","false"); });
        b.setAttribute("aria-pressed","true");
        scope.querySelectorAll(":scope > .view").forEach(function(v){
          v.classList.toggle("panel-hidden", v.dataset.view !== b.dataset.view);
        });
      });
    });
  });

  /* ---------- подсказка к уровню доступа ---------- */
  var lvlText = {
    hostLvl: ["Только каталог sandbox/, без сети и запуска команд.",
              "Чтение исходников фреймворка, запись — только в sandbox/.",
              "Чтение и запись в каталоге проекта; правка исходников — через deploy-сессию.",
              "Любые файлы хоста и произвольные команды оболочки. На рабочей машине не рекомендуется."],
    metaLvl: ["Только имя модели и температура генерации.",
              "Плюс лимиты памяти и глубина контекста.",
              "Плюс включение и отключение интерфейсов, перезапуск и остановка системы.",
              "Плюс собственные навыки: агент пишет скрипты и регистрирует их в ядре."]
  };
  document.querySelectorAll("select.lvl").forEach(function(sel){
    var out = document.getElementById(sel.dataset.hint);
    function sync(){ out.textContent = lvlText[sel.dataset.hint][+sel.value]; }
    sel.addEventListener("change", sync);
    sync();
  });

  /* ---------- поля секретов ---------- */
  function syncSec(inp){
    var box = inp.closest(".sec");
    var s = box && box.querySelector(".s");
    if (!s) return;
    var filled = inp.value.trim() !== "";
    s.textContent = filled ? "задан" : "пусто";
    s.className = filled ? "s set" : "s";
  }
  document.addEventListener("input", function(e){
    if (e.target.matches(".sec input")) syncSec(e.target);
  });
  document.querySelectorAll(".sec input").forEach(syncSec);

  function bindEye(btn){
    btn.addEventListener("click", function(){
      var inp = btn.parentElement.querySelector("input");
      var shown = btn.getAttribute("aria-pressed") === "true";
      inp.type = shown ? "password" : "text";
      btn.setAttribute("aria-pressed", shown ? "false" : "true");
      btn.setAttribute("aria-label", shown ? "Показать значение" : "Скрыть значение");
    });
  }
  document.querySelectorAll(".icobtn.eye").forEach(bindEye);

  var keyList = document.getElementById("keyList"), addKey = document.getElementById("addKey");

  function renumber(){
    if (!keyList) return;
    var rows = keyList.querySelectorAll(".sec");
    rows.forEach(function(r, i){ r.querySelector(".n").textContent = "LLM_API_KEY_" + (i + 1); });
    keyList.querySelectorAll(".delkey").forEach(function(b){ b.disabled = rows.length < 2; });
  }

  function bindDel(btn){
    btn.addEventListener("click", function(){
      var row = btn.closest(".sec");
      if (keyList && keyList.querySelectorAll(".sec").length > 1) { row.remove(); renumber(); structural++; refreshSavebar(); }
    });
  }
  if (keyList) keyList.querySelectorAll(".delkey").forEach(bindDel);

  if (addKey && keyList) addKey.addEventListener("click", function(){
    var row = keyList.querySelector(".sec").cloneNode(true);
    var inp = row.querySelector("input");
    inp.value = ""; inp.type = "password"; inp.placeholder = "вставьте ключ";
    syncSec(inp);
    var eye = row.querySelector(".eye"); eye.setAttribute("aria-pressed", "false");
    bindEye(eye); bindDel(row.querySelector(".delkey"));
    keyList.appendChild(row); renumber(); structural++; refreshSavebar(); inp.focus();
  });
  renumber();

  /* ---------- модель эмбеддингов ---------- */
  /* Рекомендованные пары «размерность / порог» из docs/yaml/settings/vector_db.md.
     Смешивать векторы разной размерности база не умеет, поэтому при смене модели
     обязательно менять vector_size и стирать каталог векторной базы. */
  var EMBEDDINGS = {
    "intfloat/multilingual-e5-large":
      {size: 1024, threshold: 0.85, ram: "~2,2 ГБ"},
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2":
      {size: 768,  threshold: 0.75, ram: "~1,0 ГБ"},
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2":
      {size: 384,  threshold: 0.65, ram: "~300 МБ"}
  };

  var embModel = document.getElementById("embModel"),
      embWarn  = document.getElementById("embWarn"),
      embInitial = null;

  function embField(key){
    return document.querySelector('[data-cfg="settings:system.db.vector.' + key + '"]');
  }

  function applyEmbeddingPreset(){
    var rec = EMBEDDINGS[embModel.value];
    if (!rec) return;
    var size = embField("vector_size"), thr = embField("similarity_threshold");
    if (size) { size.value = rec.size; size.dispatchEvent(new Event("input", {bubbles:true})); }
    if (thr)  { thr.value = rec.threshold; thr.dispatchEvent(new Event("input", {bubbles:true})); }
    showEmbeddingWarning();
  }

  function showEmbeddingWarning(){
    if (!embWarn) return;
    var changed = embInitial !== null && embModel.value !== embInitial;
    embWarn.hidden = !changed;
    if (changed) {
      embWarn.textContent = "Размерность и порог подставлены рекомендованные ("
        + EMBEDDINGS[embModel.value].ram + " памяти). База не умеет хранить векторы разной "
        + "размерности — после сохранения сотрите векторную базу на вкладке «База данных», "
        + "иначе агент не запустится. Прежние знания и мысли будут потеряны.";
    }
  }

  if (embModel) {
    embModel.addEventListener("change", applyEmbeddingPreset);
  }

  /* ---------- температура: нелинейный ползунок ---------- */
  /* 0.10…1.00 — левая половина, 1.00…3.00 — правая, чтобы 1.00 стояла по центру */
  var tempRange = document.getElementById("tempRange"),
      tempValue = document.getElementById("tempValue");

  function tempFromPos(pos){
    var t = pos <= 100 ? 0.10 + (pos / 100) * 0.90
                       : 1.00 + ((pos - 100) / 100) * 2.00;
    return Math.round(t * 100) / 100;
  }
  function posFromTemp(t){
    t = Math.min(3, Math.max(0.1, t));
    return Math.round(t <= 1 ? (t - 0.10) / 0.90 * 100
                             : 100 + (t - 1) / 2 * 100);
  }

  if (tempRange && tempValue) {
    tempRange.addEventListener("input", function(){
      tempValue.value = tempFromPos(+tempRange.value).toFixed(2);
      tempValue.dispatchEvent(new Event("input", {bubbles:true}));
    });
    tempValue.addEventListener("input", function(){
      var t = parseFloat(tempValue.value);
      if (!isNaN(t)) tempRange.value = posFromTemp(t);
    });
    tempValue.addEventListener("blur", function(){
      var t = parseFloat(tempValue.value);
      if (isNaN(t)) t = 1;
      t = Math.min(3, Math.max(0.1, Math.round(t * 100) / 100));
      tempValue.value = t.toFixed(2);
      tempRange.value = posFromTemp(t);
    });
    tempRange.value = posFromTemp(parseFloat(tempValue.value));
  }

  /* ---------- боковая панель отражает текущие настройки ---------- */
  var railName   = document.getElementById("railName"),
      railModel  = document.getElementById("railModel"),
      railAccess = document.getElementById("railAccess"),
      agentName  = document.getElementById("agentName");

  /* подписи уровней host.os.access_level; отдельная шкала от meta.access_level */
  var OS_LEVELS = ["SANDBOX", "OBSERVER", "OPERATOR", "ROOT"];

  function agentTitle(){
    return agentName ? (agentName.value.trim() || "без имени") : "Агент";
  }

  function syncRail(){
    var nm = agentName ? (agentName.value.trim() || "без имени") : "";
    if (railName) railName.textContent = nm;
    document.querySelectorAll(".agent-title").forEach(function(el){ el.textContent = nm; });
    if (nm) document.title = "JAWL · Консоль агента " + nm;
    if (railModel) {
      var main = document.querySelector('select[data-model-role="main"]');
      railModel.textContent = main && main.value ? main.value : "не выбрана";
    }
    if (railAccess) {
      var lvl = document.querySelector('select.lvl[data-hint="hostLvl"]');
      railAccess.textContent = lvl ? OS_LEVELS[+lvl.value] : "—";
    }
  }

  if (agentName) agentName.addEventListener("input", syncRail);
  document.addEventListener("change", function(e){
    if (!e.target.matches) return;
    if (e.target.matches('select[data-model-role="main"], select.lvl[data-hint="hostLvl"]')) syncRail();
  });

  /* ---------- редакторы списков (каталоги, ленты, голоса) ---------- */
  document.addEventListener("click", function(e){
    var add = e.target.closest && e.target.closest(".lst-add");
    if (add) {
      var box = document.getElementById(add.dataset.list);
      if (!box) return;
      var proto = box.querySelector(".lst-row");
      var row;
      if (proto) {
        row = proto.cloneNode(true);
        row.querySelectorAll("input").forEach(function(i){ i.value = ""; });
      } else {
        /* список пуст — собираем строку по числу колонок */
        row = document.createElement("div");
        row.className = "lst-row";
        var cols = +(box.dataset.cols || 1);
        for (var i = 0; i < cols; i++) row.appendChild(document.createElement("input"));
        row.querySelectorAll("input").forEach(function(i){ i.type = "text"; });
        var del = document.createElement("button");
        del.type = "button"; del.className = "icobtn danger lst-del";
        del.setAttribute("aria-label", "Удалить строку");
        del.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 5l14 14M19 5L5 19"/></svg>';
        row.appendChild(del);
      }
      box.appendChild(row);
      structural++;
      refreshSavebar();
      row.querySelector("input").focus();
      return;
    }
    var del = e.target.closest && e.target.closest(".lst-del");
    if (del) {
      del.closest(".lst-row").remove();
      structural++;
      refreshSavebar();
    }
  });

  /* ---------- подсказки, выводимые из других полей консоли ---------- */
  function secretFilled(name){
    var found = false;
    document.querySelectorAll(".sec").forEach(function(box){
      var n = box.querySelector(".n");
      if (n && n.textContent === name) {
        var inp = box.querySelector("input");
        if (inp && inp.value.trim()) found = true;
      }
    });
    return found;
  }

  function syncDerivedHints(){
    var gh = document.getElementById("ghAgentAccount"),
        ghHint = document.getElementById("ghHint");
    if (gh && ghHint) {
      var on = gh.getAttribute("aria-checked") === "true";
      if (!on) ghHint.textContent = "Только публичное чтение, 60 запросов в час. Токен не используется.";
      else ghHint.textContent = secretFilled("GITHUB_TOKEN")
        ? "Полный доступ, 5000 запросов в час."
        : "Нужен GITHUB_TOKEN — без него интерфейс не поднимется.";
      ghHint.classList.toggle("warn-hint", on && !secretFilled("GITHUB_TOKEN"));
    }

    var se = document.getElementById("searchEngine"),
        seHint = document.getElementById("searchHint");
    if (se && seHint) {
      var needsKey = se.value === "tavily";
      if (!needsKey) seHint.textContent = "Без ключа, но легко упирается в лимиты Cloudflare.";
      else seHint.textContent = secretFilled("TAVILY_API_KEY")
        ? "Ключ задан."
        : "Нужен TAVILY_API_KEY — иначе поиск не заработает.";
      seHint.classList.toggle("warn-hint", needsKey && !secretFilled("TAVILY_API_KEY"));
    }

    var mm = document.getElementById("isMultimodal"),
        vHint = document.getElementById("visionHint");
    if (vHint) {
      var ok = mm && mm.getAttribute("aria-checked") === "true";
      vHint.textContent = ok
        ? "Параметры LLM разрешают изображения — интерфейс поднимется."
        : "Выключено llm.is_multimodal («Параметры → Личность и LLM»). При запуске интерфейс будет отключён принудительно.";
      vHint.classList.toggle("warn-hint", !ok);
    }
  }

  document.addEventListener("input",  syncDerivedHints);
  document.addEventListener("change", syncDerivedHints);
  /* тумблеры не шлют события — их обработчики зовут markDirty(), туда и цепляемся */
  syncDerivedHints();

  /* ---------- список доступных моделей ---------- */
  /* единственный источник правды для всех полей выбора модели:
     select'ы пусты в разметке и наполняются отсюда */
  var modelList = document.getElementById("modelList"),
      addModel  = document.getElementById("addModel"),
      structural = 0;

  var ROLES = [
    {key:"main",  label:"основная",      cls:"acc"},
    {key:"swarm", label:"рой",           cls:"on"},
    {key:"tot",   label:"дерево",        cls:"vio"},
    {key:"sub",   label:"подсознание",   cls:"warn"}
  ];
  var ROLE_FULL = {
    main:"основная модель", swarm:"модель субагентов",
    tot:"дерево мыслей", sub:"подсознание"
  };
  function roleLabel(key){ return ROLE_FULL[key] || key; }

  function modelRows(){ return modelList ? modelList.querySelectorAll(".mdl") : []; }
  function modelSelects(){ return document.querySelectorAll("select[data-model-role]"); }

  function syncModels(){
    if (!modelList) return;
    var names = [];
    modelRows().forEach(function(row){
      var v = row.querySelector("input").value.trim();
      if (v && names.indexOf(v) === -1) names.push(v);
    });

    modelSelects().forEach(function(sel){
      var want = sel.dataset.modelValue || "";
      sel.textContent = "";
      /* назначенной модели может не быть в списке — не теряем значение молча */
      if (want && names.indexOf(want) === -1) {
        var miss = document.createElement("option");
        miss.value = want;
        miss.textContent = want + " — нет в списке";
        sel.appendChild(miss);
      }
      names.forEach(function(n){
        var o = document.createElement("option");
        o.value = n; o.textContent = n;
        sel.appendChild(o);
      });
      if (!sel.querySelector("option")) {
        var none = document.createElement("option");
        none.value = ""; none.textContent = "список пуст";
        sel.appendChild(none);
      }
      sel.value = want;
      if (sel.value !== want) sel.selectedIndex = 0;
      sel.dataset.modelValue = sel.value;
    });

    paintRoles();
    syncRail();
  }

  function paintRoles(){
    if (!modelList) return;
    var used = {};
    modelSelects().forEach(function(sel){
      (used[sel.value] = used[sel.value] || []).push(sel.dataset.modelRole);
    });
    var total = modelRows().length;

    modelRows().forEach(function(row){
      var name = row.querySelector("input").value.trim();
      var box  = row.querySelector(".roles");
      var mine = used[name] || [];
      box.textContent = "";
      ROLES.forEach(function(r){
        if (mine.indexOf(r.key) === -1) return;
        var b = document.createElement("span");
        b.className = "badge " + r.cls;
        b.textContent = r.label;
        b.title = roleLabel(r.key);
        box.appendChild(b);
      });

      var del = row.querySelector(".delmodel");
      del.disabled = mine.length > 0 || total < 2;
      del.title = mine.length
        ? "Занята: " + mine.map(roleLabel).join(", ") + ". Сначала назначьте другую модель."
        : (total < 2 ? "Нужна хотя бы одна модель" : "Удалить модель");
    });
  }

  if (modelList) {
    modelRows().forEach(function(row){
      row.querySelector("input").dataset.prev = row.querySelector("input").value.trim();
    });

    /* переименование модели тянет за собой роли, которые на неё указывали */
    modelList.addEventListener("input", function(e){
      if (!e.target.matches(".mdl input")) return;
      var prev = e.target.dataset.prev, next = e.target.value.trim();
      if (prev) modelSelects().forEach(function(sel){
        if (sel.dataset.modelValue === prev) sel.dataset.modelValue = next;
      });
      e.target.dataset.prev = next;
      syncModels();
    });

    modelList.addEventListener("click", function(e){
      var btn = e.target.closest(".delmodel");
      if (!btn || btn.disabled) return;
      btn.closest(".mdl").remove();
      structural++;
      syncModels();
      refreshSavebar();
    });

    if (addModel) addModel.addEventListener("click", function(){
      var row = modelRows()[0].cloneNode(true);
      var inp = row.querySelector("input");
      inp.value = ""; inp.placeholder = "провайдер/модель"; inp.dataset.prev = "";
      row.querySelector(".roles").textContent = "";
      modelList.appendChild(row);
      structural++;
      syncModels();
      refreshSavebar();
      inp.focus();
    });
  }

  document.addEventListener("change", function(e){
    if (!e.target.matches || !e.target.matches("select[data-model-role]")) return;
    e.target.dataset.modelValue = e.target.value;
    paintRoles();
  });

  syncModels();

  /* ---------- доступные имена для нестандартных контролов ---------- */
  /* role="switch" без имени скринридер читает как пустоту, поэтому имя
     берём из подписи рядом: .fn в поле, .dn у мотиватора, h3 в шапке карточки */
  function controlName(el){
    var field = el.closest(".field");
    if (field) {
      var fn = field.querySelector(".fn");
      if (fn && fn.textContent.trim()) return fn.textContent.trim();
      var fd = field.querySelector(".fd");
      if (fd && fd.textContent.trim()) return fd.textContent.trim();
    }
    var head = el.closest(".drive-head");
    if (head) { var dn = head.querySelector(".dn"); if (dn) return dn.textContent.trim(); }
    var kv = el.closest(".kv");
    if (kv) { var k = kv.querySelector(".k"); if (k) return k.textContent.trim(); }
    var hdr = el.closest("header");
    if (hdr) { var h3 = hdr.querySelector("h3"); if (h3) return h3.textContent.trim(); }
    var sec = el.closest(".sec");
    if (sec) { var n = sec.querySelector(".n"); if (n) return n.textContent.trim(); }
    return "";
  }

  document.querySelectorAll('[role="switch"], .field input, .field select, .drive-cfg input')
    .forEach(function(el){
      if (el.hasAttribute("aria-label") || el.closest(".icobtn")) return;
      var name = controlName(el);
      if (name) el.setAttribute("aria-label", name);
    });

  /* клик по подписи поля фокусирует его контрол — замена <label for> без правки разметки */
  document.querySelectorAll(".field .fl").forEach(function(fl){
    var field = fl.closest(".field");
    var ctl = field && field.querySelector(".fc input, .fc select, .fc textarea, .fc [role=switch]");
    if (!ctl) return;
    fl.classList.add("clickable");
    fl.addEventListener("click", function(){
      if (ctl.hasAttribute("role")) ctl.click(); else ctl.focus();
    });
  });

  /* ---------- бейджи вкл/выкл ---------- */
  document.querySelectorAll(".badge.tgl").forEach(function(b){
    b.addEventListener("click", function(){
      var on = !b.classList.contains("on");
      b.classList.toggle("on", on);
      b.classList.toggle("off", !on);
      b.textContent = on ? "вкл" : "выкл";
      b.setAttribute("aria-checked", on ? "true" : "false");
      if (b.closest(".ifc")) applyIfcFilter();
      markDirty(b);
    });
  });

  /* ---------- тумблеры ---------- */
  document.querySelectorAll(".sw").forEach(function(sw){
    sw.setAttribute("tabindex","0");
    var drive = sw.closest(".drive");
    function flip(){
      if (sw.getAttribute("aria-disabled") === "true") return;
      var on = sw.getAttribute("aria-checked") !== "true";
      sw.setAttribute("aria-checked", on ? "true" : "false");
      if (drive) drive.setAttribute("data-on", on ? "true" : "false");
      markDirty(sw);
    }
    sw.addEventListener("click", flip);
    sw.addEventListener("keydown", function(e){ if(e.key === " " || e.key === "Enter"){ e.preventDefault(); flip(); }});
  });

  /* ---------- фильтр и поиск по интерфейсам ---------- */
  var ifcGrid   = document.getElementById("ifcGrid"),
      ifcList   = document.getElementById("ifcList"),
      ifcSearch = document.getElementById("ifcSearch"),
      ifcEmpty  = document.getElementById("ifcEmpty"),
      ifcChips  = document.querySelectorAll("[data-ifc]"),
      ifcSelected = 0;

  function ifcIsOn(card){
    var t = card.querySelector("header .badge.tgl");
    return !t || t.getAttribute("aria-checked") === "true";
  }

  function ifcCards(){ return ifcGrid ? ifcGrid.querySelectorAll(".ifc") : []; }
  function ifcRows(){ return ifcList ? ifcList.querySelectorAll(".ifc-item") : []; }

  /* строки списка — представление карточек; источник состояния остаётся в карточке */
  function buildIfcList(){
    if (!ifcList || !ifcGrid) return;
    ifcCards().forEach(function(card, i){
      var row = document.createElement("button");
      row.type = "button";
      row.className = "ifc-item";
      row.setAttribute("role", "tab");
      row.setAttribute("aria-selected", i === 0 ? "true" : "false");

      var name = card.querySelector("h3").textContent;
      var nm = document.createElement("span");
      nm.className = "nm";
      nm.textContent = name;
      if (card.dataset.events === "true") {
        var ev = document.createElement("span");
        ev.className = "ev";
        ev.textContent = "СОБ";
        ev.title = "Поставляет события в шину";
        nm.appendChild(ev);
      }

      var sw = document.createElement("span");
      sw.className = "sw";
      sw.setAttribute("role", "switch");
      sw.setAttribute("tabindex", "0");
      sw.setAttribute("aria-label", "Включить: " + name);

      row.appendChild(nm);
      row.appendChild(sw);
      ifcList.insertBefore(row, ifcEmpty);

      row.addEventListener("click", function(e){
        if (e.target.closest(".sw")) return;
        selectIfc(i);
      });

      function flip(e){
        e.stopPropagation();
        var badge = card.querySelector("header .badge.tgl");
        if (badge) badge.click();
      }
      sw.addEventListener("click", flip);
      sw.addEventListener("keydown", function(e){
        if (e.key === " " || e.key === "Enter") { e.preventDefault(); flip(e); }
      });
    });

    /* стрелками — по списку, как в остальной консоли */
    ifcList.addEventListener("keydown", function(e){
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      if (e.target.closest(".sw")) return;
      var visible = [];
      ifcRows().forEach(function(r, i){ if (!r.hidden) visible.push(i); });
      var pos = visible.indexOf(ifcSelected);
      if (pos < 0) return;
      e.preventDefault();
      var next = visible[pos + (e.key === "ArrowDown" ? 1 : -1)];
      if (next === undefined) return;
      selectIfc(next);
      ifcRows()[next].focus();
    });
  }

  function selectIfc(i){
    var cards = ifcCards();
    if (!cards.length) return;
    ifcSelected = i;
    cards.forEach(function(c, k){ c.hidden = k !== i; });
    ifcRows().forEach(function(r, k){
      r.setAttribute("aria-selected", k === i ? "true" : "false");
    });
  }

  /**
   * Показывает карточку интерфейса, в которой живёт нужная настройка.
   *
   * Нужно, чтобы из чата можно было попасть прямо к выключателю терминала:
   * искать его среди восемнадцати карточек вручную — то ещё занятие. Фильтр и
   * поиск сбрасываем, иначе карточка может оказаться отфильтрованной.
   */
  function revealInterface(path){
    var control = document.querySelector('[data-cfg="interfaces:' + path + '"]');
    var card = control && control.closest(".ifc");
    if (!card) return false;

    if (ifcSearch) ifcSearch.value = "";
    var all = document.querySelector('[data-ifc="all"]');
    if (all) all.click();

    var index = Array.prototype.indexOf.call(ifcCards(), card);
    if (index < 0) return false;
    selectIfc(index);
    card.scrollIntoView({block: "nearest"});
    return true;
  }

  function applyIfcFilter(){
    if (!ifcGrid) return;
    var cards  = ifcCards(), rows = ifcRows();
    var active = document.querySelector('[data-ifc][aria-pressed="true"]');
    var mode   = active ? active.dataset.ifc : "all";
    var q      = ifcSearch ? ifcSearch.value.toLowerCase().trim() : "";
    var shown  = 0, counts = {all:0, on:0, off:0, events:0};
    var firstVisible = -1, selectedVisible = false;

    cards.forEach(function(card, i){
      var on = ifcIsOn(card);
      counts.all++;
      counts[on ? "on" : "off"]++;
      if (card.dataset.events === "true") counts.events++;

      var okMode = mode === "all"
        || (mode === "on"  && on)
        || (mode === "off" && !on)
        || (mode === "events" && card.dataset.events === "true");
      var okQ = !q || (card.dataset.name + " " + card.textContent).toLowerCase().indexOf(q) > -1;
      var visible = okMode && okQ;

      if (rows[i]) {
        rows[i].hidden = !visible;
        var sw = rows[i].querySelector(".sw");
        if (sw) sw.setAttribute("aria-checked", on ? "true" : "false");
      }
      if (visible) {
        shown++;
        if (firstVisible < 0) firstVisible = i;
        if (i === ifcSelected) selectedVisible = true;
      }
    });

    /* выбранный ушёл под фильтр — показываем первый оставшийся */
    if (firstVisible < 0) cards.forEach(function(c){ c.hidden = true; });
    else selectIfc(selectedVisible ? ifcSelected : firstVisible);

    ifcChips.forEach(function(c){
      var n = c.querySelector(".n");
      if (n) n.textContent = counts[c.dataset.ifc];
    });
    var tabCount = document.getElementById("ifcTabCount");
    if (tabCount) tabCount.textContent = counts.on + "/" + counts.all;
    if (ifcEmpty) ifcEmpty.hidden = shown > 0;
  }

  ifcChips.forEach(function(c){
    c.addEventListener("click", function(){
      ifcChips.forEach(function(x){ x.setAttribute("aria-pressed","false"); });
      c.setAttribute("aria-pressed","true");
      applyIfcFilter();
    });
  });
  buildIfcList();
  if (ifcSearch) {
    ifcSearch.addEventListener("input", applyIfcFilter);
    ifcSearch.addEventListener("keydown", function(e){
      if (e.key === "Escape") { ifcSearch.value = ""; applyIfcFilter(); }
    });
  }
  applyIfcFilter();

  /* ---------- чипы уровней логов ---------- */
  var lvChips = document.querySelectorAll(".chip[data-lv]");
  lvChips.forEach(function(c){
    c.addEventListener("click", function(){
      lvChips.forEach(function(x){ x.setAttribute("aria-pressed","false"); });
      c.setAttribute("aria-pressed","true");
      filterLogs();
    });
  });

  /* ---------- кардиограмма такта ---------- */
  var pulseline = document.getElementById("pulseline"),
      trace     = document.getElementById("trace");

  var SAMPLES = 600;                 /* совпадает с viewBox, 1 отсчёт на единицу x */
  var MID = 15, STEP_MS = 38;        /* ~26 кадров в секунду, окно истории те же ~23 с */
  var BEAT_STEPS = 42;               /* длина удара в отсчётах — ширина на экране прежняя */
  var wave = new Array(SAMPLES).fill(0);

  /* форма удара: небольшая волна, резкий пик, откат, пологий хвост */
  var BEAT = [0, .04, .10, .05, 0, -.10, .55, 1, -.38, -.06, .05, .16, .20, .13, .05, .01, 0];
  var beatQueue = [];

  var reduceMotion = window.matchMedia
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var BEAT_CAP = BEAT_STEPS * 6;     /* дольше этого очередь не копим */

  /* Удары дописываются в конец очереди: за один опрос может прийти сразу
     несколько событий, и каждое должно быть видно отдельным всплеском. */
  function pushBeat(amp){
    var q = [], i, x, a, b, f;
    for (i = 0; i < BEAT_STEPS; i++) {
      x = i / (BEAT_STEPS - 1) * (BEAT.length - 1);
      a = Math.floor(x); b = Math.min(a + 1, BEAT.length - 1); f = x - a;
      q.push((BEAT[a] * (1 - f) + BEAT[b] * f) * amp);
    }
    if (beatQueue.length > BEAT_CAP) return;
    beatQueue = beatQueue.concat(q);
  }

  function drawTrace(){
    if (!trace) return;
    var pts = new Array(SAMPLES), i;
    for (i = 0; i < SAMPLES; i++) {
      pts[i] = i + "," + (MID - wave[i] * 14).toFixed(2);
    }
    trace.setAttribute("points", pts.join(" "));
  }

  var lastStep = 0, breath = 0;
  function stepWave(now){
    if (now - lastStep < STEP_MS) return;
    lastStep = now;
    wave.shift();
    if (beatQueue.length) {
      wave.push(beatQueue.shift());
    } else if (pulseline && pulseline.dataset.state === "off") {
      wave.push(0);                      /* агент остановлен — ровная линия */
    } else {
      /* во сне — медленное дыхание: полоса живёт, а удары читаются контрастом */
      breath += 0.02;
      wave.push(Math.sin(breath) * 0.055 + (Math.random() - .5) * 0.012);
    }
    drawTrace();
  }

  function frame(now){
    stepWave(now);
    requestAnimationFrame(frame);
  }

  if (trace) {
    drawTrace();
    if (!reduceMotion) requestAnimationFrame(frame);
  }

  /* ---------- такт: состояние восстанавливается из журнала ----------

     ПОДКЛЮЧЕНО. Своего состояния агент наружу не отдаёт — он живёт в другом
     процессе, а `AgentState` держится в его памяти. Поэтому шапка читает
     /api/tick, где сервер разбирает logs/main.log и повторяет расчёт момента
     следующего пробуждения из src/l3_agent/heartbeat.py.               */

  var wakeIn = document.getElementById("wakeIn"),
      wakeKey = document.getElementById("wakeKey"),
      pulseWord = document.getElementById("pulseWord"),
      pulseAct = document.getElementById("pulseAct"),
      stepEl = document.getElementById("reactStep"),
      dot = document.getElementById("pulseDot");

  var running = true,          /* агент запущен — узнаём из /api/agent/status */
      starting = false,
      stopping = false,
      tickSeq = 0,             /* последний отрисованный всплеск */
      beatsPrimed = false,     /* первый ответ только догоняет счётчик */
      wakeDeadline = null,     /* локальный дедлайн: отсчёт идёт между опросами */
      lastTick = null;

  /* уровень события задаёт цвет ленты */
  var LEVEL_TONE = {CRITICAL:"crit", HIGH:"high"};

  function pad(n){ return (n < 10 ? "0" : "") + n; }

  function fmtLeft(sec){
    if (sec == null) return "—";
    sec = Math.max(0, Math.round(sec));
    var h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), r = sec % 60;
    return h ? h + ":" + pad(m) + ":" + pad(r) : pad(m) + ":" + pad(r);
  }

  /* Событие называется по-английски и заглавными — в шапке это шум.
     Показываем понятную причину пробуждения, незнакомое — как есть. */
  var REASONS = {
    HEARTBEAT: "плановый такт",
    SYSTEM_CORE_START: "запуск ядра",
    AIOGRAM_MESSAGE_INCOMING: "сообщение в Telegram",
    OS_FILE_MODIFIED: "файл изменён",
    OS_FILE_CREATED: "файл создан",
    OS_FILE_DELETED: "файл удалён",
    OS_DIR_MODIFIED: "каталог изменён"
  };
  function reasonText(name){
    if (!name) return "";
    return REASONS[name] || name.toLowerCase().replace(/_/g, " ");
  }

  /* Единственное место, где рисуется остаток. Считаем от дедлайна: относительное
     число из ответа устаревает, и повторная отрисовка тем же состоянием
     подставляла бы его как свежее. */
  function paintWake(){
    if (!wakeIn) return;
    if (wakeDeadline == null) { wakeIn.textContent = "—"; return; }

    var left = (wakeDeadline - Date.now()) / 1000;
    /* Срок вышел, а строки о пробуждении в журнале ещё нет: агент может
       задержаться на доли секунды, да и опрос идёт не непрерывно. Замереть
       на «00:00» значило бы утверждать, что он спит ровно ноль секунд. */
    wakeIn.textContent = left <= 0 ? "вот-вот" : fmtLeft(left);
  }

  function setPhaseWord(word, tone){
    if (pulseWord) pulseWord.textContent = word;
    if (dot) dot.style.background = tone;
  }

  function showActivity(text){
    if (!pulseAct) return;
    if (text) { pulseAct.textContent = text; pulseAct.hidden = false; }
    else { pulseAct.hidden = true; pulseAct.textContent = ""; }
  }

  /* ----- всплески: рисуем только события, которых ещё не видели ----- */
  function drawBeats(events){
    if (!events || !events.length) return;
    events.forEach(function(ev){
      if (ev.seq <= tickSeq) return;
      tickSeq = ev.seq;
      pushBeat(ev.amp || 0.4);
      if (pulseline && (ev.kind === "wake" || ev.kind === "interrupt")) {
        var tone = LEVEL_TONE[ev.level];
        if (tone) pulseline.dataset.prio = tone; else delete pulseline.dataset.prio;
      }
    });
  }

  function paintTick(t){
    lastTick = t;

    /* Сервер хранит последние всплески, и при загрузке страницы они все выглядят
       новыми. Первый ответ только догоняет счётчик: рисовать удары, которых
       пользователь не застал, — то же враньё, что и выдуманный пульс. */
    if (!beatsPrimed) { beatsPrimed = true; tickSeq = t.seq || 0; }
    else drawBeats(t.events);

    if (!running) return;                /* остановленный рисуется отдельно */
    /* Процесс поднят, но журнал ещё не сказал ни слова — рисовать нечего,
       за это состояние отвечает опрос статуса процесса. */
    if (starting && t.phase !== "starting") return;

    if (t.phase === "wake") {
      setPhaseWord("Думает", "var(--sage)");
      if (pulseline) pulseline.dataset.state = "wake";
      if (wakeKey) wakeKey.textContent = "Разбужен";
      if (wakeIn) wakeIn.textContent = reasonText(t.reason) || "сейчас";
      if (stepEl) stepEl.textContent = t.step
        ? t.step + " / " + (t.maxSteps || "?") : "—";
      wakeDeadline = null;

      var act = t.activity || {};
      showActivity(act.text ? act.title + ": " + act.text : act.title);
      return;
    }

    if (t.phase === "sleep") {
      if (t.continuous) {
        setPhaseWord("Непрерывный цикл", "var(--sage)");
        if (wakeKey) wakeKey.textContent = "Пробуждение через";
        if (wakeIn) wakeIn.textContent = "без пауз";
        wakeDeadline = null;
      } else {
        setPhaseWord(t.sleepDepth && t.sleepDepth !== "normal" ? "Глубокий сон" : "Сон",
                     "var(--amber)");
        if (wakeKey) wakeKey.textContent = "Пробуждение через";
        /* Остаток относительный, поэтому привязываем его к моменту, когда ответ
           пришёл. Иначе повторная отрисовка тем же состоянием (её делает
           опрос статуса процесса) отматывала бы отсчёт назад. */
        wakeDeadline = t.wakeInSec == null
          ? null : (t.receivedAt || Date.now()) + t.wakeInSec * 1000;
        paintWake();
      }
      if (pulseline) { pulseline.dataset.state = "sleep"; delete pulseline.dataset.prio; }
      if (stepEl) stepEl.textContent = "—";
      showActivity("");
      return;
    }

    if (t.phase === "starting") {
      /* pid-файл появляется на первой секунде, а подъём идёт минутами: дольше
         всего качается модель эмбеддингов. Показываем, чем он занят, иначе
         шапка молчала бы всё это время. */
      setPhaseWord("Запускается", "var(--amber)");
      if (pulseline) { pulseline.dataset.state = "sleep"; delete pulseline.dataset.prio; }
      if (wakeKey) wakeKey.textContent = "Подъём";
      if (wakeIn) wakeIn.textContent = "идёт";
      if (stepEl) stepEl.textContent = "—";
      wakeDeadline = null;
      showActivity(t.bootStep || "поднимаются подсистемы");
      return;
    }

    if (t.phase === "off") {
      /* журнал говорит «остановлен», а процесс жив: агент ещё поднимается
         либо только что завершил работу — не выдаём это за рабочее состояние */
      setPhaseWord("Не в такте", "var(--dim)");
      if (pulseline) { pulseline.dataset.state = "sleep"; delete pulseline.dataset.prio; }
      if (wakeIn) wakeIn.textContent = "—";
      if (stepEl) stepEl.textContent = "—";
      wakeDeadline = null;
      showActivity("");
      return;
    }

    /* журнал есть, но узнаваемых строк в нём пока нет */
    setPhaseWord("Ожидание", "var(--amber)");
    if (wakeIn) wakeIn.textContent = "—";
    if (stepEl) stepEl.textContent = "—";
    wakeDeadline = null;
    showActivity(t.note || "");
  }

  function refreshTick(){
    return api.tickState().then(function(res){
      if (res && res.ok) { res.receivedAt = Date.now(); paintTick(res); }
    }).catch(function(){ /* сервер мог перезапускаться — молчим */ });
  }

  /* Отсчёт идёт локально каждую секунду, опрос — реже: так цифра не дёргается,
     а журнал не читается вхолостую. */
  setInterval(function(){
    if (!running || starting || wakeDeadline == null) return;
    paintWake();
  }, 1000);

  setInterval(function(){
    if (document.visibilityState === "visible") refreshTick();
  }, 1500);
  refreshTick();

  /* Пока вкладка скрыта, опроса нет — местный отсчёт за это время успевает
     устареть. Возвращаемся: сначала показываем правду, потом продолжаем. */
  document.addEventListener("visibilitychange", function(){
    if (document.visibilityState === "visible") refreshTick();
  });

  /* ---------- запуск и остановка агента ---------- */
  var btnStart = document.getElementById("btnStart"),
      btnStop  = document.getElementById("btnStop");

  function setRunning(on){
    running = on;
    if (btnStart) btnStart.disabled = on;
    if (btnStop)  btnStop.disabled  = !on;

    if (!on) {
      wakeDeadline = null;
      if (pulseWord) pulseWord.textContent = "Остановлен";
      if (dot) { dot.style.background = "var(--dim)"; dot.classList.remove("live"); }
      if (wakeIn) wakeIn.textContent = "—";
      if (wakeKey) wakeKey.textContent = "Пробуждение через";
      if (stepEl) stepEl.textContent = "—";
      if (pulseline) { pulseline.dataset.state = "off"; delete pulseline.dataset.prio; }
      showActivity("");
    } else {
      if (dot) dot.classList.add("live");
      /* дальше всё нарисует состояние такта из журнала */
      if (lastTick) paintTick(lastTick); else refreshTick();
    }
  }

  /* состояние берём у сервера: агента могли запустить и из CLI */
  var agentBusy = false;

  function lockRunButtons(busy, label){
    agentBusy = busy;
    if (btnStart) { btnStart.disabled = busy || running; }
    if (btnStop)  { btnStop.disabled  = busy || !running; }
    if (busy && label && pulseWord) pulseWord.textContent = label;
  }

  function refreshAgentStatus(){
    if (agentBusy) return Promise.resolve();
    return api.agentStatus().then(function(res){
      if (!res || !res.ok) return;
      if (res.running !== running) setRunning(res.running);
      if (btnStart) btnStart.disabled = res.running;
      if (btnStop)  btnStop.disabled  = !res.running;

      /* на первом старте агент качает модель эмбеддингов и минутами не
         регистрируется — показываем это состояние, а не «остановлен» */
      var wasBusy = starting || stopping;
      starting = !!res.starting;
      stopping = !!res.stopping;

      if (stopping) {
        /* pid-файл агент удаляет последней строкой, а сворачивается ещё
           секунду-другую. Без этого состояния завершение выглядело запуском. */
        if (pulseWord) pulseWord.textContent = "Останавливается";
        if (dot) dot.style.background = "var(--amber)";
        if (wakeKey) wakeKey.textContent = "Состояние";
        if (wakeIn) wakeIn.textContent = "закрывает базы";
        if (stepEl) stepEl.textContent = "—";
        wakeDeadline = null;
        showActivity("");
      } else if (starting && (!lastTick || lastTick.phase !== "starting")) {
        /* процесс поднят, но журнал ещё молчит */
        if (pulseWord) pulseWord.textContent = "Запускается";
        if (dot) dot.style.background = "var(--amber)";
        if (wakeIn) wakeIn.textContent = "—";
        if (stepEl) stepEl.textContent = "—";
        wakeDeadline = null;
        showActivity("");
      } else if (wasBusy && res.running && lastTick) {
        paintTick(lastTick);               /* поднялся — снова ведём по журналу */
      }

      if (!uptimeEl) return;
      if (res.stopping)            uptimeEl.textContent = "останавливается";
      else if (res.starting)       uptimeEl.textContent = "запускается";
      else if (!res.running)       uptimeEl.textContent = "остановлен";
      else if (res.uptimeSec != null) uptimeEl.textContent = formatUptime(res.uptimeSec);
    }).catch(function(){ /* сервер мог не подняться — молчим, не мусорим тостами */ });
  }

  function formatUptime(sec){
    var d = Math.floor(sec / 86400), h = Math.floor(sec % 86400 / 3600),
        m = Math.floor(sec % 3600 / 60);
    function p(n){ return (n < 10 ? "0" : "") + n; }
    return (d ? d + " д " : "") + p(h) + ":" + p(m);
  }

  var uptimeEl = document.getElementById("railUptime");

  if (btnStart) btnStart.addEventListener("click", function(){
    lockRunButtons(true, "Запуск…");
    api.startAgent().then(function(res){
      agentBusy = false;
      if (res && res.ok) {
        setRunning(true);
        toast("Агент запущен" + (res.pid ? " (PID " + res.pid + ")" : ""));
      } else {
        setRunning(false);
        toast("Не запустился: " + ((res && res.error) || "неизвестная ошибка"));
        if (res && res.detail) notice("Из logs/startup/startup_error.log: " + res.detail, "err");
      }
      refreshAgentStatus();
    }).catch(function(err){
      agentBusy = false;
      toast("Не запустился: " + err.message);
      refreshAgentStatus();
    });
  });

  if (btnStop) btnStop.addEventListener("click", function(){
    lockRunButtons(true, "Остановка…");
    api.stopAgent().then(function(res){
      agentBusy = false;
      setRunning(false);
      toast(res && res.forced ? "Агент не ответил вовремя — процесс снят"
                              : "Агент остановлен");
      refreshAgentStatus();
    }).catch(function(err){
      agentBusy = false;
      toast("Не остановился: " + err.message);
      refreshAgentStatus();
    });
  });

  refreshAgentStatus();
  setInterval(refreshAgentStatus, 4000);

  /* ---------- вкладка «База данных» ----------

     ПОДКЛЮЧЕНО. Счётчики читаются из самих хранилищ (/api/db/stats). Три базы
     ведут себя по-разному при работающем агенте: SQLite и коллекции Qdrant
     читаются, а Kuzu держит файл графа монопольно — тогда сервер присылает
     locked, и мы говорим об этом прямо, а не рисуем ноль.               */

  var dbNotice = document.getElementById("dbNotice");
  var dbAgentRunning = true;

  function setText(id, text){
    var el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function fmtSize(bytes){
    if (bytes == null) return "—";
    if (bytes < 1024) return bytes + " Б";
    if (bytes < 1048576) return (bytes / 1024).toFixed(0) + " КБ";
    if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + " МБ";
    return (bytes / 1073741824).toFixed(2) + " ГБ";
  }

  /* «3 из 5» честнее, чем «3/5»: лимит — это потолок модуля из settings.yaml */
  function withLimit(count, limit){
    if (count == null) return "—";
    return limit ? count + " из " + limit : String(count);
  }

  function plural(n, one, few, many){
    var a = Math.abs(n) % 100, b = a % 10;
    if (a > 10 && a < 20) return many;
    if (b > 1 && b < 5) return few;
    if (b === 1) return one;
    return many;
  }

  function renderDbStats(res){
    if (!res || !res.ok) {
      if (dbNotice) {
        dbNotice.hidden = false;
        dbNotice.className = "notice err";
        dbNotice.textContent = "Счётчики не прочитались: " + ((res && res.error) || "нет ответа");
      }
      return;
    }

    dbAgentRunning = !!res.agentRunning;
    if (dbNotice) {
      dbNotice.hidden = !dbAgentRunning;
      dbNotice.className = "notice";
      dbNotice.textContent = "Агент запущен — очистка недоступна: базы он держит "
        + "открытыми, и правка разошлась бы с его состоянием в памяти. "
        + "Счётчики при этом читаются, кроме графа.";
    }
    document.querySelectorAll(".btn.wipe").forEach(function(btn){
      btn.disabled = dbAgentRunning;
    });

    /* ---- реляционная ---- */
    var sql = res.sql || {}, counts = sql.counts || {}, limits = sql.limits || {};
    setText("dbMental", withLimit(counts.mental_states, limits.mental_states));
    setText("dbTasks",  withLimit(counts.tasks, limits.tasks));
    setText("dbNotes",  withLimit(counts.notes, limits.notes));
    setText("dbTraits", withLimit(counts.personality_traits, limits.personality_traits));

    var drives = sql.drives || {};
    setText("dbDrives", sql.exists
      ? drives.fundamental + " фунд. · " + withLimit(drives.custom, limits.drives) + " своих"
      : "—");

    /* ---- векторная ---- */
    var vector = res.vector || {}, vc = vector.counts || {};
    ["knowledge", "thoughts"].forEach(function(name){
      var id = "db" + name.charAt(0).toUpperCase() + name.slice(1);
      var n = vc[name];
      setText(id, n == null ? "—" : n + " " + plural(n, "запись", "записи", "записей"));
    });

    /* ---- скачанные модели эмбеддингов ---- */
    renderEmbeddings(res.embeddings || {});

    /* ---- граф ---- */
    var graph = res.graph || {};
    if (!graph.exists) {
      setText("dbConcepts", "базы ещё нет");
    } else if (graph.locked) {
      setText("dbConcepts", "агент держит базу");
    } else {
      var n = (graph.counts || {}).concepts;
      setText("dbConcepts", n == null ? "—"
        : n + " " + plural(n, "понятие", "понятия", "понятий"));
    }

    /* ---- каталоги ---- */
    var dirs = res.dirs || {};
    ["interfaces", "sandbox"].forEach(function(key){
      var info = dirs[key] || {};
      var id = key === "interfaces" ? "dbCache" : "dbSandbox";
      setText(id, !info.exists ? "нет каталога"
        : info.files + " " + plural(info.files, "файл", "файла", "файлов")
          + " · " + fmtSize(info.sizeBytes));
    });
  }

  /* Веса моделей весят сотни мегабайт и остаются после смены модели в
     настройках. Список строится на лету: какие каталоги лежат в кэше, такие и
     показываем. Кнопки подхватывает общий обработчик .btn.wipe. */
  var embList = document.getElementById("embList");

  function embRow(model){
    var row = document.createElement("div");
    row.className = "field";

    var label = document.createElement("div");
    label.className = "fl";
    var name = document.createElement("div");
    name.className = "fn";
    name.textContent = model.title;
    label.appendChild(name);

    if (model.active) {
      var note = document.createElement("div");
      note.className = "fd";
      note.textContent = "используется сейчас";
      label.appendChild(note);
    }

    var controls = document.createElement("div");
    controls.className = "fc";
    var size = document.createElement("span");
    size.className = "dbcount";
    size.textContent = fmtSize(model.sizeBytes);
    controls.appendChild(size);

    var btn = document.createElement("button");
    btn.className = "btn danger wipe";
    btn.textContent = "Удалить";
    btn.dataset.scope = "embeddings." + model.dir;
    btn.disabled = dbAgentRunning;
    /* Активную модель удалять можно — она просто скачается заново. Но сказать
       об этом стоит заранее: это сотни мегабайт и долгий первый запуск. */
    btn.title = model.active
      ? "Модель используется сейчас. После удаления она скачается заново при следующем запуске — это долго."
      : "Модель не используется. Освободится " + fmtSize(model.sizeBytes) + ".";
    controls.appendChild(btn);

    row.appendChild(label);
    row.appendChild(controls);
    return row;
  }

  function renderEmbeddings(info){
    if (!embList) return;
    embList.textContent = "";

    var models = info.models || [];
    if (!models.length) {
      var empty = document.createElement("div");
      empty.className = "hint";
      empty.textContent = info.exists
        ? "Веса ещё не скачаны — это произойдёт при первом запуске агента."
        : "Каталога с моделями пока нет.";
      embList.appendChild(empty);
      return;
    }

    models.forEach(function(model){ embList.appendChild(embRow(model)); });

    /* настройка указывает на модель, которой на диске нет */
    if (!info.activeDownloaded && info.activeModel) {
      var warn = document.createElement("div");
      warn.className = "hint";
      warn.textContent = "Выбранная модель «" + info.activeModel
        + "» ещё не скачана — она загрузится при следующем запуске агента.";
      embList.appendChild(warn);
    }
  }

  function refreshDbStats(){
    return api.loadDbStats().then(renderDbStats).catch(function(err){
      renderDbStats({ok: false, error: err.message});
    });
  }

  refreshDbStats();
  setInterval(function(){
    /* вкладка открыта и видима — иначе незачем ходить по базам */
    if (document.visibilityState !== "visible") return;
    var panel = document.querySelector('.panel[data-panel="db"]');
    if (panel && !panel.classList.contains("panel-hidden")) refreshDbStats();
  }, 5000);

  /* очистка необратима — просим второе нажатие вместо модального окна */
  var armedTimer;
  function disarm(btn){
    btn.removeAttribute("data-armed");
    btn.textContent = btn.dataset.label;
  }
  document.addEventListener("click", function(e){
    var btn = e.target.closest && e.target.closest(".btn.wipe");
    if (!btn) return;
    if (!btn.dataset.label) btn.dataset.label = btn.textContent;

    if (btn.getAttribute("data-armed") === "true") {
      disarm(btn);
      clearTimeout(armedTimer);
      btn.disabled = true;
      api.wipe(btn.dataset.scope).then(function(res){
        btn.disabled = dbAgentRunning;
        if (res && res.ok) {
          toast("Очищено: " + res.label + " — " + res.detail);
          refreshDbStats();
        } else {
          toast("Не очищено: " + ((res && res.error) || "ошибка сервера"));
        }
      }).catch(function(err){
        btn.disabled = dbAgentRunning;
        toast("Не очищено: " + err.message);
      });
      return;
    }
    document.querySelectorAll('.btn.wipe[data-armed="true"]').forEach(disarm);
    btn.setAttribute("data-armed", "true");
    btn.textContent = "Точно? Нажмите ещё раз";
    clearTimeout(armedTimer);
    armedTimer = setTimeout(function(){ disarm(btn); }, 4000);
  });

  document.addEventListener("click", function(e){
    var btn = e.target.closest && e.target.closest(".btn.opendir");
    if (!btn) return;
    api.openDir(btn.dataset.dir);
  });

  /* ---------- чат ----------

     ПОДКЛЮЧЕНО. Разговор идёт через собственный терминальный канал агента
     (src/l2_interfaces/host/terminal) — тот же, которым пользуется CLI-чат.
     Сообщение поднимает событие HOST_TERMINAL_MESSAGE уровня CRITICAL, то есть
     будит агента немедленно, не дожидаясь такта.                          */

  var send = document.getElementById("chatSend"),
      input = document.getElementById("chatInput"),
      log = document.getElementById("chatlog"),
      chatEmpty = document.getElementById("chatEmpty"),
      chatNotice = document.getElementById("chatNotice");

  var chatSeq = 0,          /* последняя показанная реплика */
      chatStop = null,      /* как отписаться от потока */
      chatOnline = false,
      chatLoaded = false;

  /* Время приходит от агента строкой «2026-08-25 02:31:54». Разбираем сами:
     Date его на части браузеров не парсит, а показывать надо дату и часы. */
  function splitStamp(stamp){
    var m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(stamp || "");
    if (!m) return {date: "", time: stamp || ""};
    return {date: m[3] + "." + m[2] + "." + m[1], time: m[4] + ":" + m[5]};
  }

  function bubble(message){
    var mine = message.sender === "User";
    var node = document.createElement("div");
    node.className = "msg " + (mine ? "op" : "ag");

    var who = document.createElement("div");
    who.className = "who";
    var name = document.createElement("span");
    /* имя агента ведётся полем «Имя агента» — помечаем, чтобы оно обновлялось */
    if (!mine) name.className = "agent-title";
    name.textContent = mine ? "Пользователь" : message.sender;
    who.appendChild(name);

    var when = splitStamp(message.time);
    var dateEl = document.createElement("span");
    dateEl.className = "d";
    dateEl.textContent = when.date;
    var timeEl = document.createElement("span");
    timeEl.className = "t";
    timeEl.textContent = when.time;
    who.appendChild(dateEl);
    who.appendChild(timeEl);

    var body = document.createElement("div");
    body.className = "txt";
    /* агент отвечает Markdown-ом; разметку не разбираем, но абзацы сохраняем */
    String(message.text || "").split(/\n{2,}/).forEach(function(part){
      var p = document.createElement("p");
      p.textContent = part.trim();
      if (p.textContent) body.appendChild(p);
    });
    if (!body.childNodes.length) {
      var p = document.createElement("p");
      p.textContent = message.text || "";
      body.appendChild(p);
    }

    node.appendChild(who);
    node.appendChild(body);
    return node;
  }

  function atChatBottom(){
    return log.scrollHeight - log.scrollTop - log.clientHeight < 60;
  }

  /**
   * Дописывает реплики, пропуская уже показанные.
   *
   * Отсев по номеру обязателен: своё сообщение появляется сразу из ответа на
   * отправку, но у потока на сервере **свой** курсор, и про уже показанное он
   * не знает — та же реплика приходила вторым экземпляром. Заодно это спасает
   * от повторов при переподключении потока.
   *
   * У истории из файла номеров нет — она читается один раз и проходит как есть.
   */
  function appendMessages(rows){
    if (!rows || !rows.length) return;

    var fresh = rows.filter(function(row){
      if (row.seq == null) return true;
      if (row.seq <= chatSeq) return false;
      chatSeq = row.seq;
      return true;
    });
    if (!fresh.length) return;

    var follow = atChatBottom();
    if (chatEmpty) { chatEmpty.remove(); chatEmpty = null; }
    fresh.forEach(function(row){ log.appendChild(bubble(row)); });
    /* не выдёргиваем из-под пользователя, если он листает вверх */
    if (follow) log.scrollTop = log.scrollHeight;
  }

  var CHAT_STATES = {
    online: "",
    connecting: "Подключаюсь к терминалу агента…",
    offline: "Нет связи с агентом. Запустите его — переписка отправится, когда он поднимется.",
    idle: "Связь не установлена."
  };

  /* Весь чат держится на интерфейсе «Терминал»: выключен — агент не поднимает
     TCP-сервер, и разговаривать не через что. Это настройка, а не сбой, поэтому
     говорим об этом прямо и ведём туда, где её включить. */
  var TERMINAL_OFF =
    "Чат не работает: интерфейс «Терминал» выключен. Через него агент и "
    + "разговаривает с оператором. Включите его и перезапустите агента — "
    + "интерфейсы поднимаются при старте.";

  function chatJumpButton(){
    var btn = document.createElement("button");
    btn.className = "btn";
    btn.type = "button";
    btn.textContent = "Открыть настройку";
    btn.addEventListener("click", function(){
      var tab = document.querySelector('.tab[data-tab="interfaces"]');
      if (tab) tab.click();
      revealInterface("host.terminal.enabled");
    });
    return btn;
  }

  function applyChatStatus(status){
    if (!status) return;

    /* Флаг приходит независимо от состояния соединения: причина «выключено»
       важнее, чем то, дошли мы до попытки подключиться или нет. */
    var disabled = status.terminalEnabled === false;
    chatOnline = !disabled && status.state === "online";

    if (input) {
      input.disabled = !chatOnline;
      input.placeholder = disabled
        ? "Интерфейс «Терминал» выключен"
        : (chatOnline
            ? "Сообщение агенту — Enter отправит, Shift+Enter перенесёт строку"
            : "Агент недоступен");
    }
    if (send) send.disabled = !chatOnline;

    if (!chatNotice) return;

    if (disabled) {
      chatNotice.hidden = false;
      chatNotice.className = "notice err";
      chatNotice.textContent = TERMINAL_OFF + " ";
      chatNotice.appendChild(chatJumpButton());
      return;
    }

    var text = CHAT_STATES[status.state] || "";
    if (status.state === "offline" && status.error) text += " (" + status.error + ")";
    chatNotice.hidden = !text;
    chatNotice.className = status.state === "offline" ? "notice err" : "notice";
    chatNotice.textContent = text;
  }

  function loadChat(){
    if (chatLoaded) return Promise.resolve();
    chatLoaded = true;
    return api.loadChat().then(function(res){
      if (!res || !res.ok) return;
      if (chatEmpty) {
        chatEmpty.textContent = res.history.length
          ? "" : "Переписки пока нет. Напишите первым — агент проснётся сразу.";
      }
      appendMessages(res.history);
      log.scrollTop = log.scrollHeight;
      applyChatStatus(res.status);

      /* История из файла и буфер потока перекрываются: агент записывает в файл
         те же реплики, что уже разошлись по подписчикам. Догоняем счётчик
         сервера, иначе всё показанное придёт из потока ещё раз. */
      chatSeq = res.status.seq || 0;
    }).catch(function(err){
      if (chatEmpty) chatEmpty.textContent = "Не удалось прочитать переписку: " + err.message;
    });
  }

  function startChatStream(){
    if (chatStop) return;
    chatStop = api.subscribeChat(chatSeq, function(data){
      applyChatStatus(data.status);
      appendMessages(data.messages);
    });
  }

  function stopChatStream(){
    if (!chatStop) return;
    chatStop();
    chatStop = null;
  }

  var chatSending = false;

  /**
   * Отправляет содержимое поля.
   *
   * Два условия, без которых сообщения задваиваются и рвутся:
   *
   * * повторный вызов во время отправки отбрасывается. Кнопку блокировал
   *   `disabled`, но Enter вызывает `submit()` напрямую — второе нажатие
   *   отправляло тот же текст ещё раз;
   * * поле очищается сразу, а не по ответу сервера. Иначе набранное за время
   *   ответа смешивалось с уже отправленным: в переписке появлялись обрывки
   *   вроде одиночной буквы.
   *
   * Если не дошло — текст возвращается в поле, чтобы не пропал набранный.
   */
  function submit(){
    if (chatSending) return;
    var text = input.value.trim();
    if (!text) return;

    chatSending = true;
    send.disabled = true;
    input.value = "";

    function done(){
      chatSending = false;
      send.disabled = !chatOnline;
    }

    api.sendMessage(text).then(function(res){
      done();
      if (res && res.ok) {
        appendMessages([res.message]);
        log.scrollTop = log.scrollHeight;
      } else {
        input.value = text;
        toast("Не отправилось: " + ((res && res.error) || "ошибка сервера"));
      }
    }).catch(function(err){
      done();
      input.value = text;
      toast("Не отправилось: " + err.message);
    });
  }

  if (send) send.addEventListener("click", submit);
  if (input) input.addEventListener("keydown", function(e){
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  });

  /* Подписка держится, пока выбран раздел «Чат»: для агента открытый поток
     означает «оператор держит терминал открытым», и врать ему об этом не стоит.

     А вот на visibilityState не смотрим. Свёрнутое окно браузера — это не
     «оператор ушёл»: чат по-прежнему открыт, как остаётся открытым окно CLI.
     Иначе каждый переход на соседнюю вкладку слал бы агенту пару
     «терминал закрыт» / «терминал открыт», а событие открытия ещё и ускоряет
     ему пробуждение. */
  function syncChatSubscription(){
    var panel = document.querySelector('.panel[data-panel="chat"]');
    if (panel && !panel.classList.contains("panel-hidden")) {
      loadChat().then(startChatStream);
    } else {
      stopChatStream();
    }
  }

  document.querySelectorAll(".tab").forEach(function(t){
    t.addEventListener("click", syncChatSubscription);
  });
  window.addEventListener("beforeunload", stopChatStream);
  syncChatSubscription();

  /* ---------- логи ---------- */
  var logBox = document.getElementById("logBox");
  var MAX_RECORDS = 400;

  function span(cls, text){
    var e = document.createElement("span");
    if (cls) e.className = cls;
    e.textContent = text;
    return e;
  }

  function recNode(r){
    var d = document.createElement("div");
    d.className = "rec";
    d.dataset.lv = r.lv;
    d.appendChild(span("ts", r.ts));
    d.appendChild(document.createTextNode(" - "));
    d.appendChild(span("lg", r.logger));
    d.appendChild(document.createTextNode(" - "));
    d.appendChild(span("lv lv-" + r.lv, r.lv));
    d.appendChild(document.createTextNode(" - "));

    /* сообщение обычно начинается с [Компонента] — выделяем его */
    var m = /^(\[[^\]]+\])([\s\S]*)$/.exec(r.text);
    if (m) {
      d.appendChild(span("cmp", m[1]));
      d.appendChild(span("msg", m[2]));
    } else {
      d.appendChild(span("msg", r.text));
    }
    return d;
  }

  /* формат строки main.log:
     2026-08-21 04:24:10.787 - JAWL.Agent - WARNING - [LLM] All keys in cooldown.
     запись может быть многострочной — продолжение приклеивается к предыдущей */
  var REC_RE = /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) - ([\w.]+) - (\w+) - ([\s\S]*)$/;

  var records = [];

  function logNodeFor(rec){
    var node = recNode(rec);
    node.__rec = rec;
    return node;
  }

  /* Строка без метки времени — продолжение предыдущей записи. Многострочные
     блоки ([Thoughts], отчёты субагентов) приходят разными порциями, поэтому
     склейка должна переживать границу между ними. */
  function pushLine(line){
    var m = REC_RE.exec(line);
    if (m) {
      var rec = {ts: m[1], logger: m[2], lv: m[3], text: m[4]};
      records.push(rec);
      var empty = logBox.querySelector(".empty");
      logBox.insertBefore(logNodeFor(rec), empty || null);
      return;
    }
    var last = records[records.length - 1];
    if (!last) return;                     // хвост записи, начало которой не застали
    last.text += "\n" + line;
    var nodes = logBox.querySelectorAll(".rec");
    var node = nodes[nodes.length - 1];
    if (node) logBox.replaceChild(logNodeFor(last), node);
  }

  function appendLogText(text){
    if (!logBox || !text) return;
    var pinned = logBox.scrollHeight - logBox.scrollTop - logBox.clientHeight < 24;

    text.replace(/\r/g, "").split("\n").forEach(function(line, i, all){
      if (i === all.length - 1 && line === "") return;   // хвостовой перевод строки
      pushLine(line);
    });

    while (records.length > MAX_RECORDS) {
      records.shift();
      var first = logBox.querySelector(".rec");
      if (first) first.remove();
    }
    filterLogs();
    if (pinned) scrollLogsToEnd();
  }

  var logOffset = 0, unsubscribeLogs = null;

  function startLogStream(){
    if (unsubscribeLogs) return;
    unsubscribeLogs = api.subscribeLogs(logOffset, function(chunk){
      if (paused) return;                  // на паузе новое не подмешиваем
      logOffset = chunk.offset;
      appendLogText(chunk.text);
    });
  }

  var LOAD_LOGS_MARKER = true;

  api.loadLogs().then(function(res){
    if (!res || !res.ok) return;
    logOffset = res.offset || 0;
    if (res.missing) {
      logBox.textContent = "";
      var note = document.createElement("div");
      note.className = "empty";
      note.textContent = "Файла logs/main.log ещё нет — он появится после первого запуска агента.";
      logBox.appendChild(note);
      return;
    }
    logBox.textContent = "";
    records = [];
    appendLogText(res.text);
    scrollLogsToEnd();
    startLogStream();
  }).catch(function(err){
    if (!logBox) return;
    logBox.textContent = "";
    var note = document.createElement("div");
    note.className = "empty";
    note.textContent = "Журнал не читается: " + err.message;
    logBox.appendChild(note);
  });

  /* при первой отрисовке панель ещё скрыта и высоты равны нулю,
     поэтому к концу файла прокручиваем и при открытии вкладки */
  function scrollLogsToEnd(){
    if (logBox) logBox.scrollTop = logBox.scrollHeight;
  }

  function filterLogs(){
    if (!logBox) return;
    var active = document.querySelector('.chip[data-lv][aria-pressed="true"]');
    var lv = active ? active.dataset.lv : "all";
    var q = (document.getElementById("logSearch") || {value:""}).value.toLowerCase().trim();
    var shown = 0, counts = {all:0, ERROR:0, WARNING:0, DEBUG:0};

    logBox.querySelectorAll(".rec").forEach(function(rec){
      counts.all++;
      if (counts[rec.dataset.lv] !== undefined) counts[rec.dataset.lv]++;
      var okLv = (lv === "all") || (rec.dataset.lv === lv);
      var okQ = !q || rec.textContent.toLowerCase().indexOf(q) > -1;
      var visible = okLv && okQ;
      rec.hidden = !visible;
      if (visible) shown++;
    });

    document.querySelectorAll(".chip[data-lv] .n").forEach(function(n){
      n.textContent = counts[n.parentElement.dataset.lv];
    });
    var tabCount = document.getElementById("logTabCount");
    if (tabCount) tabCount.textContent = counts.ERROR ? counts.ERROR + "⚠" : "";

    var empty = logBox.querySelector(".empty");
    if (!shown) {
      if (!empty) {
        empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "Под фильтр ничего не подошло";
        logBox.appendChild(empty);
      }
      empty.hidden = false;
    } else if (empty) {
      empty.hidden = true;
    }
  }

  var logSearch = document.getElementById("logSearch");
  if (logSearch) {
    logSearch.addEventListener("input", filterLogs);
    logSearch.addEventListener("keydown", function(e){
      if (e.key === "Escape") { logSearch.value = ""; filterLogs(); }
    });
  }

  var pause = document.getElementById("logPause"), paused = false;

  if (pause) pause.addEventListener("click", function(){
    paused = !paused;
    pause.setAttribute("aria-pressed", paused ? "true" : "false");
    pause.textContent = paused ? "Возобновить" : "Пауза";
  });

  var logsTab = document.querySelector('.tab[data-tab="logs"]');
  if (logsTab) logsTab.addEventListener("click", scrollLogsToEnd);


  /* ---------- кнопки, ждущие бэкенд ---------- */
  document.addEventListener("click", function(e){
    var b = e.target.closest && e.target.closest("[data-action]");
    if (!b) return;
    switch (b.dataset.action) {
      case "reload-interfaces": api.reloadInterfaces(); break;
      case "check-llm-keys":    api.checkLlmKeys();     break;
      case "download-logs":     api.downloadLogs();     break;
      case "reveal":            api.openDir(b.dataset.path || ""); break;
    }
  });

  /* ---------- конфигурация: чтение, применение, запись ---------- */
  /* Привязка идёт по атрибуту data-cfg, тот же ключ лежит в src/web/schema.py.
     Поля без data-cfg ещё не интегрированы и живут на значениях из разметки. */
  var cfgNotice = document.getElementById("cfgNotice"),
      cfgLoaded = false;

  function notice(text, kind){
    if (!cfgNotice) return;
    cfgNotice.textContent = text;
    cfgNotice.className = "notice" + (kind ? " " + kind : "");
    cfgNotice.hidden = !text;
  }

  function boundControls(){ return document.querySelectorAll("[data-cfg]"); }

  function writeControl(el, value){
    if (el.hasAttribute("role")) {
      var on = !!value;
      el.setAttribute("aria-checked", on ? "true" : "false");
      var drive = el.closest(".drive");
      if (drive) drive.setAttribute("data-on", on ? "true" : "false");
      /* бейдж «вкл/выкл» в шапке карточки несёт состояние ещё и классом с текстом */
      if (el.classList.contains("tgl")) {
        el.classList.toggle("on", on);
        el.classList.toggle("off", !on);
        el.textContent = on ? "вкл" : "выкл";
      }
      return;
    }
    el.value = value === null || value === undefined ? "" : String(value);
  }

  function readControl(el){
    if (el.hasAttribute("role")) return el.getAttribute("aria-checked") === "true";
    if (el.type === "number") {
      var n = parseFloat(el.value);
      return isNaN(n) ? el.value : n;
    }
    return el.value;
  }

  /* списки, у которых есть свой редактор, наполняются отдельно */
  function fillModelList(names){
    if (!modelList || !names) return;
    var proto = modelList.querySelector(".mdl");
    if (!proto) return;
    var clean = proto.cloneNode(true);
    modelList.textContent = "";
    (names.length ? names : [""]).forEach(function(name){
      var row = clean.cloneNode(true);
      var inp = row.querySelector("input");
      inp.value = name;
      inp.dataset.prev = name;
      inp.disabled = false;
      row.querySelector(".roles").textContent = "";
      modelList.appendChild(row);
    });
  }

  function fillKeyList(values){
    if (!keyList || !values) return;
    var proto = keyList.querySelector(".sec");
    if (!proto) return;
    var clean = proto.cloneNode(true);
    keyList.textContent = "";
    (values.length ? values : [""]).forEach(function(value){
      var row = clean.cloneNode(true);
      var inp = row.querySelector("input");
      inp.value = value;
      inp.type = "password";
      inp.disabled = false;
      keyList.appendChild(row);
      bindEye(row.querySelector(".eye"));
      bindDel(row.querySelector(".delkey"));
      syncSec(inp);
    });
    renumber();
  }

  /* редакторы списков: строки могут быть строками или объектами (RSS-ленты) */
  function fillEditableList(id, items){
    var box = document.getElementById(id);
    if (!box || !items) return;
    var cols = +(box.dataset.cols || 1);
    box.textContent = "";
    items.forEach(function(item){
      var values = cols > 1 ? Object.keys(item).map(function(k){ return item[k]; })
                            : [item];
      var row = document.createElement("div");
      row.className = "lst-row";
      for (var i = 0; i < cols; i++) {
        var inp = document.createElement("input");
        inp.type = "text";
        inp.value = values[i] === undefined ? "" : values[i];
        row.appendChild(inp);
      }
      var del = document.createElement("button");
      del.type = "button"; del.className = "icobtn danger lst-del";
      del.setAttribute("aria-label", "Удалить строку");
      del.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 5l14 14M19 5L5 19"/></svg>';
      row.appendChild(del);
      box.appendChild(row);
    });
  }

  /* ПОДКЛЮЧЕНО. Версия фреймворка из src/__init__.py — её отдаёт /api/config. */
  function applyVersion(version){
    var el = document.getElementById("brandVer");
    if (!el) return;
    el.textContent = version ? "v" + version : "";
    el.title = version ? "Версия фреймворка (src/__init__.py)" : "";
  }

  function applyConfig(cfg){
    var values = cfg.values || {}, lists = cfg.lists || {};

    applyVersion(cfg.version);

    boundControls().forEach(function(el){
      var key = el.getAttribute("data-cfg");
      if (!(key in values)) return;
      writeControl(el, values[key]);
      el.disabled = false;
      el.removeAttribute("aria-disabled");
    });

    fillModelList(lists.modelList);
    fillKeyList(lists.keyList);
    Object.keys(lists).forEach(function(id){
      if (id === "modelList" || id === "keyList") return;
      fillEditableList(id, lists[id]);
    });

    /* селекты моделей наполняются из списка — их значение восстанавливаем после */
    document.querySelectorAll("select[data-model-role][data-cfg]").forEach(function(sel){
      var key = sel.getAttribute("data-cfg");
      if (key in values) sel.dataset.modelValue = values[key] === null ? "" : String(values[key]);
      sel.disabled = false;
    });
    syncModels();

    if (embModel) {
      /* модель из файла может не совпасть ни с одной рекомендованной */
      var known = embModel.value === values["settings:system.db.vector.embedding_model"];
      if (!known) {
        var opt = document.createElement("option");
        opt.value = values["settings:system.db.vector.embedding_model"] || "";
        opt.textContent = (opt.value || "не задана") + " — не из рекомендованных";
        embModel.insertBefore(opt, embModel.firstChild);
        embModel.value = opt.value;
      }
      embInitial = embModel.value;
      if (embWarn) embWarn.hidden = true;
    }

    var tv = document.getElementById("tempValue"), tr = document.getElementById("tempRange");
    if (tv && tr) {
      var t = parseFloat(tv.value);
      if (!isNaN(t)) { tv.value = t.toFixed(2); tr.value = posFromTemp(t); }
      tr.disabled = false;
    }

    listBaseline = snapshotLists();
    syncRail();
    applyIfcFilter();
    syncDerivedHints();
    cfgLoaded = true;
    notice("");
    /* снимок только по полям конфигурации: до ответа сервера они были пустыми,
       и всё прочитанное считалось бы изменённым. Правки в других местах
       (например, у своих мотиваторов) этот снимок трогать не должен */
    capture("[data-cfg]");
    refreshSavebar();
  }

  /* Списки шлём целиком, но только изменившиеся: иначе правка одного
     мотиватора переписывала бы все три конфига и врала бы в отчёте. */
  var listBaseline = {};

  function snapshotLists(){
    var snap = {};
    Object.keys(gatherLists()).forEach(function(id){
      snap[id] = JSON.stringify(gatherLists()[id]);
    });
    return snap;
  }

  function gatherLists(){
    var lists = {};
    if (modelList) {
      lists.modelList = [].map.call(modelList.querySelectorAll(".mdl input"),
        function(i){ return i.value.trim(); }).filter(Boolean);
    }
    if (keyList) {
      lists.keyList = [].map.call(keyList.querySelectorAll(".sec input"),
        function(i){ return i.value.trim(); }).filter(Boolean);
    }
    var LIST_KEYS = {lstFeeds: ["name", "url"]};
    document.querySelectorAll(".lst[id]").forEach(function(box){
      var cols = +(box.dataset.cols || 1);
      var keys = LIST_KEYS[box.id];
      lists[box.id] = [].map.call(box.querySelectorAll(".lst-row"), function(row){
        var vals = [].map.call(row.querySelectorAll("input"), function(i){ return i.value.trim(); });
        if (cols === 1 || !keys) return vals[0] || "";
        var obj = {};
        keys.forEach(function(k, i){ obj[k] = vals[i] || ""; });
        return obj;
      }).filter(function(x){
        return typeof x === "string" ? x : Object.keys(x).some(function(k){ return x[k]; });
      });
    });
    return lists;
  }

  function collectChanges(){
    var values = {}, n = 0;
    baseline.forEach(function(was, el){
      if (ctlValue(el) === was) return;
      n++;
      var key = el.getAttribute && el.getAttribute("data-cfg");
      if (key) values[key] = readControl(el);
    });

    var current = gatherLists(), lists = {};
    Object.keys(current).forEach(function(id){
      if (JSON.stringify(current[id]) !== listBaseline[id]) lists[id] = current[id];
    });

    return {values: values, lists: lists, count: n};
  }

  api.loadConfig().then(applyConfig).catch(function(err){
    notice("Бэкенд не отвечает (" + err.message + "). Запустите: python -m src.web — "
         + "поля вкладки останутся заблокированными.", "err");
  });

  /* ---------- мотиваторы ---------- */
  /* Дефицит нигде не хранится: он растёт со временем, поэтому шкалы
     обновляются по таймеру. Свои мотиваторы существуют только в базе — их
     карточки строятся здесь, фундаментальные уже есть в разметке. */
  var drivesBox = document.getElementById("drivesBox"),
      drivesNote = document.getElementById("drivesNote"),
      customBuilt = false;

  function meterTone(deficit){
    if (deficit >= 70) return "clay";
    if (deficit >= 40) return "amber";
    return "sage";
  }

  function paintDrive(block, drive){
    var label = block.querySelector(".dv");
    if (label) label.textContent = "дефицит " + drive.deficit.toFixed(0) + "%";

    /* Описание приходит из базы. У фундаментальных фреймворк держит его
       по-английски — сервер подставляет русский перевод, как и для названий. */
    var note = block.querySelector(".dsc");
    if (note) note.textContent = drive.description || "";

    var bar = block.querySelector(".meter i");
    if (bar) {
      bar.style.width = Math.max(0, Math.min(100, drive.deficit)) + "%";
      bar.className = meterTone(drive.deficit);
    }
  }

  function buildCustomDrive(drive){
    var block = document.createElement("div");
    block.className = "drive";
    block.dataset.on = "true";
    block.dataset.driveId = drive.id;
    block.innerHTML =
      '<div class="drive-head">' +
        '<div class="drive-t"><span class="dn"></span><span class="dv"></span></div>' +
        '<span class="badge vio">свой</span>' +
      '</div>' +
      '<div class="meter"><i class="sage" style="width:0%"></i></div>' +
      '<div class="hint dsc"></div>' +
      '<div class="drive-cfg">' +
        '<label>Рост дефицита <input type="number" min="0.5" max="100" step="0.5"' +
        ' data-drive="' + drive.id + ':decayRate"><span class="unit">%</span></label>' +
        '<label>Интервал <input type="number" min="60" max="86400" step="60"' +
        ' data-drive="' + drive.id + ':decayIntervalSec"><span class="unit">сек</span></label>' +
      '</div>';

    block.querySelector(".dn").textContent = drive.title;
    block.querySelector(".dsc").textContent = drive.description || "";
    return block;
  }

  function renderDrives(res){
    if (!drivesBox) return;

    if (!res || !res.ok) {
      if (drivesNote) {
        drivesNote.hidden = false;
        drivesNote.className = "notice err";
        drivesNote.textContent = "Мотиваторы не читаются: " + ((res && res.error) || "нет ответа");
      }
      return;
    }
    if (res.missing) {
      if (drivesNote) {
        drivesNote.hidden = false;
        drivesNote.className = "notice";
        drivesNote.textContent = "База агента ещё не создана — мотиваторы появятся после первого запуска.";
      }
      return;
    }
    if (drivesNote) drivesNote.hidden = true;

    var pending = [];

    res.drives.forEach(function(drive){
      var block;
      if (drive.key) {
        block = document.querySelector('.drive[data-key="' + drive.key + '"]');
        if (drive.pendingRestart) pending.push(drive.title);
      } else {
        block = drivesBox.querySelector('.drive[data-drive-id="' + drive.id + '"]');
        if (!block) {
          block = buildCustomDrive(drive);
          drivesBox.appendChild(block);
          var rate = block.querySelector('[data-drive$=":decayRate"]');
          var iv = block.querySelector('[data-drive$=":decayIntervalSec"]');
          rate.value = drive.decayRate;
          iv.value = drive.decayIntervalSec;
          rate.dataset.was = rate.value;
          iv.dataset.was = iv.value;
        }
      }
      if (block) paintDrive(block, drive);
    });

    /* строка исчезнувшего мотиватора: агент мог его удалить */
    drivesBox.querySelectorAll(".drive[data-drive-id]").forEach(function(block){
      var alive = res.drives.some(function(d){ return d.id === block.dataset.driveId; });
      if (!alive) block.remove();
    });

    if (pending.length && drivesNote) {
      drivesNote.hidden = false;
      drivesNote.className = "notice err";
      drivesNote.textContent = "В базе агента другие значения для: " + pending.join(", ")
        + ". Настройки из settings.yaml применятся при следующем запуске.";
    }

    if (!customBuilt) {
      customBuilt = true;
      capture("[data-drive]");         /* только что созданные поля — в снимок */
      refreshSavebar();
    }
  }

  function refreshDrives(){
    return api.loadDrives().then(renderDrives).catch(function(err){
      renderDrives({ok: false, error: err.message});
    });
  }

  function collectDriveUpdates(){
    var updates = {};
    document.querySelectorAll("[data-drive]").forEach(function(el){
      if (el.value === el.dataset.was) return;
      var parts = el.getAttribute("data-drive").split(":");
      updates[parts[0]] = updates[parts[0]] || {};
      updates[parts[0]][parts[1]] = parseFloat(el.value);
    });
    return updates;
  }

  refreshDrives();
  setInterval(function(){
    if (document.visibilityState === "visible") refreshDrives();
  }, 10000);

  /* ---------- несохранённые изменения ---------- */
  var savebar   = document.getElementById("savebar"),
      saveCount = document.getElementById("saveCount"),
      saveWhere = document.getElementById("saveWhere"),
      saveApply = document.getElementById("saveApply"),
      saveReset = document.getElementById("saveReset");

  /* редактируемые контролы конфигурации */
  var EDIT_SEL = '[data-panel="settings"] input, [data-panel="settings"] select,'
               + '[data-panel="settings"] [role="switch"],'
               + '[data-panel="interfaces"] input, [data-panel="interfaces"] select,'
               + '[data-panel="interfaces"] [role="switch"]';

  function ctlValue(el){
    if (el.hasAttribute("role")) return el.getAttribute("aria-checked");
    return el.value;
  }

  function plural(n, one, few, many){
    var m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
    return many;
  }

  var baseline = new Map();

  function trackable(el){
    if (el.type === "search" || el.type === "range") return false;
    if (el.closest(".ifc-list")) return false;   /* зеркало карточки, не отдельное значение */
    return true;
  }

  /**
   * Снимок значений для панели «Не сохранено».
   *
   * `only` ограничивает снимок теми полями, которые вызывающий код только что
   * заполнил сам. Без этого ограничения поздний снимок (конфиг и мотиваторы
   * приходят разными запросами) перезаписывал бы уже сделанную правку, и
   * панель не появлялась бы вовсе.
   */
  function capture(only){
    if (!only) {
      baseline.clear();
      structural = 0;
    }
    document.querySelectorAll(only || EDIT_SEL).forEach(function(el){
      if (trackable(el)) baseline.set(el, ctlValue(el));
    });
  }

  /* файл определяется префиксом data-cfg, а не вкладкой: секреты .env лежат
     и в «Параметрах», и в «Интерфейсах» */
  var CFG_FILES = {settings: "settings.yaml", interfaces: "interfaces.yaml", env: ".env"};

  function fileOf(el){
    if (el.hasAttribute && el.hasAttribute("data-drive")) return "базу мотиваторов";
    var key = el.getAttribute && el.getAttribute("data-cfg");
    if (key) return CFG_FILES[key.split(":")[0]] || "";
    var p = el.closest(".panel");
    return p && p.dataset.panel === "settings" ? "settings.yaml" : "interfaces.yaml";
  }

  function refreshSavebar(){
    if (!savebar) return;
    var files = {}, n = 0;
    baseline.forEach(function(was, el){
      var changed = ctlValue(el) !== was;
      var row = el.closest(".field") || el.closest(".drive-cfg label") || el.closest(".sec");
      if (!el.hasAttribute("role")) el.classList.toggle("dirty", changed);
      if (row) row.classList.toggle("dirty-row", changed);
      if (changed) { n++; files[fileOf(el)] = true; }
    });
    savebar.hidden = n === 0 && structural === 0;
    if (!n && !structural) return;
    if (structural) { files["settings.yaml"] = true; n += structural; }
    saveCount.textContent = n + " " + plural(n, "поле", "поля", "полей");
    saveWhere.textContent = Object.keys(files).join(" · ");
  }

  /* вызывается из обработчиков тумблеров и бейджей */
  function markDirty(){ refreshSavebar(); syncDerivedHints(); }

  document.addEventListener("input", function(e){
    if (!e.target.matches) return;
    if (e.target.matches(EDIT_SEL) || e.target.hasAttribute("data-drive")) refreshSavebar();
  });
  document.addEventListener("change", function(e){
    if (!e.target.matches) return;
    if (e.target.matches(EDIT_SEL) || e.target.hasAttribute("data-drive")) refreshSavebar();
  });

  var toastTimer;
  function toast(text){
    var old = document.querySelector(".toast");
    if (old) old.remove();
    var t = document.createElement("div");
    t.className = "toast";
    t.setAttribute("role", "status");
    t.textContent = text;
    document.body.appendChild(t);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function(){ t.remove(); }, 3200);
  }

  if (saveReset) saveReset.addEventListener("click", function(){
    baseline.forEach(function(was, el){
      if (el.hasAttribute("role")) {
        if (el.getAttribute("aria-checked") !== was) el.click();
      } else if (el.value !== was) {
        el.value = was;
        /* оба события: на input завязаны статусы секретов, на change — подсказки select */
        el.dispatchEvent(new Event("input",  {bubbles:true}));
        el.dispatchEvent(new Event("change", {bubbles:true}));
      }
    });
    refreshSavebar();
    applyIfcFilter();
    toast("Изменения отменены");
  });

  if (saveApply) saveApply.addEventListener("click", function(){
    if (!cfgLoaded) { toast("Конфигурация не прочитана — сохранять нечего"); return; }
    var changes = collectChanges();
    var driveUpdates = collectDriveUpdates();
    saveApply.disabled = true;
    api.saveConfig({values: changes.values, lists: changes.lists}).then(function(res){
      saveApply.disabled = false;
      if (!res || !res.ok) { toast("Не сохранено: " + ((res && res.error) || "ошибка сервера")); return; }

      var written = (res.written || []).slice();
      var afterDrives = Object.keys(driveUpdates).length
        ? api.saveDrives(driveUpdates).then(function(dr){
            if (dr && dr.ok) {
              if ((dr.updated || []).length) written.push("базу мотиваторов");
              document.querySelectorAll("[data-drive]").forEach(function(el){
                el.dataset.was = el.value;
              });
              refreshDrives();
            } else {
              toast("Мотиваторы не сохранены: " + ((dr && dr.error) || "ошибка"));
            }
          })
        : Promise.resolve();

      afterDrives.then(function(){
      listBaseline = snapshotLists();
      capture();
      refreshSavebar();
      var files = written.join(" и ");
      toast(files ? "Записано в " + files : "Изменений не потребовалось");
      });
      if (res.unknown && res.unknown.length) {
        notice("Эти поля ещё не привязаны к конфигу: " + res.unknown.join(", "), "err");
      }
    }).catch(function(err){
      saveApply.disabled = false;
      toast("Не сохранено: " + err.message);
    });
  });

  capture();
  refreshSavebar();

  /* панель нужна только на вкладках-редакторах */
  tabs.forEach(function(t){
    t.addEventListener("click", function(){
      if (!savebar) return;
      var editor = t.dataset.tab === "settings" || t.dataset.tab === "interfaces";
      savebar.classList.toggle("panel-hidden", !editor);
    });
  });

})();
