import { BridgeError } from "./errors.mjs";

const issue = (code) => ({ code });
const deskName = (status) => status?.ma2 === "logged_in" && status.show?.source === "ma2" ? status.show.name : null;
export const deskOnline = (status) => status?.ma2 === "logged_in" && !status.halted && !status.recovering;

class PlanChangedError extends BridgeError {
  constructor() {
    super({ code: "plan_context_changed" });
  }
}

export class BridgeClient {
  constructor() {
    this.state = {
      connected: false,
      bridgePhase: "bridge_disconnected",
      status: null,
      config: null,
      history: {},
      actionHistory: [],
      sceneSlot: null,
      dimSent: null,
      masterEvidence: {quality:"unknown"},
      shown: {},
      live: {},
      running: {},
      running_meta: {},
      values_meta: {},
      selected: [],
      selecting: false,
      error: null,
      feedback: null,
      master: null,
      simulation: {},
    };
    this.receipts = { values_meta: new Map(), running_meta: new Map() };
    this.listeners = new Set();
    this.pending = new Map();
    this.observations = new Map();
    this.serial = 0;
    this.context = 0;
    this.selectionSerial = 0;
    this.needsSelectionSync = false;
    this.selectionSyncPromise = null;
    this.dimReadbackFloor = -Infinity;
    this.lastReadbackAt = -Infinity;
    this.prefix = globalThis.crypto?.randomUUID?.() || String(Date.now());
  }
  getSnapshot = () => this.state;
  subscribe = (fn) => {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  };
  publish(patch = {}) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((fn) => fn());
  }
  connectionKey() {
    const { status, bridgePhase } = this.state;
    if (status?.ma2 === "tcp") return "connection.login_check";
    if (status?.ma2 === "login_failed") return "connection.login_failed";
    const phase = status?.readiness?.connection ?? bridgePhase;
    return ["bridge_disconnected", "connecting", "disconnected", "login_unconfirmed", "authenticated", "connection_error"].includes(phase)
      ? `connection.${phase}` : "connection.connecting";
  }
  blockReason(action) {
    const { status, bridgePhase, blackoutPending } = this.state;
    if (this.socket?.readyState !== 1)
      return issue(bridgePhase);
    if (!status)
      return issue("connecting");
    if (status.mock !== true && status.hall_trial !== true)
      return issue("mock_only");
    const categories = status.readiness?.actions;
    const category = Object.keys(categories || {}).find((key) => Object.hasOwn(categories[key], action));
    if (!category) {
      if (status.ma2 === "login_unknown")
        return issue("login_unconfirmed");
      return issue("readiness_unavailable");
    }
    const blocked = categories[category][action];
    if (blocked)
      return blocked.code === "recovering" && status.recovery_error
        ? { ...blocked, message: status.recovery_error } : blocked;
    if (category === "light" && status.plan_selection && status.readiness?.show?.state === "matched" &&
        this.state.config?.show !== status.readiness.show.name)
      return issue("plan_sync");
    if (blackoutPending && (category === "light" || category === "general"))
      return issue("blackout_pending");
    return null;
  }
  ready(action = "select_fixtures") {
    return this.blockReason(action) === null;
  }
  connect() {
    this.closed = false;
    clearInterval(this.evidenceTimer);
    this.evidenceTimer = setInterval(() => this.expireEvidence(), 1000);
    const socket = this.socket = new WebSocket(
      `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`,
    );
    this.publish({ bridgePhase: "connecting" });
    socket.onopen = () => {
      if (this.socket === socket) this.publish({ connected: true });
    };
    socket.onmessage = (e) => {
      if (this.socket !== socket) return;
      try {
        this.receive(JSON.parse(e.data));
      } catch {
        this.publish({ error: new BridgeError(issue("response_invalid")) });
      }
    };
    socket.onclose = () => {
      if (this.socket !== socket) return;
      this.disconnected(this.state.bridgePhase === "connection_error" ? "connection_error" : "bridge_disconnected");
      if (!this.closed) this.reconnect = setTimeout(() => this.connect(), 1500);
    };
    socket.onerror = () => {
      if (this.socket === socket) this.publish({ bridgePhase: "connection_error" });
    };
  }
  disconnect() {
    this.closed = true;
    clearTimeout(this.reconnect);
    const socket = this.socket;
    this.socket = null;
    socket?.close();
    this.disconnected();
  }
  disconnected(bridgePhase = "bridge_disconnected") {
    clearInterval(this.evidenceTimer);
    this.receipts = { values_meta: new Map(), running_meta: new Map() };
    this.context++;
    this.selectionSerial++;
    this.needsSelectionSync = this.state.selected.length > 0;
    this.selectionSyncPromise = null;
    this.valuesRevision = -1;
    this.dimReadbackFloor = this.lastReadbackAt;
    for (const p of this.pending.values()) {
      clearTimeout(p.timer);
      p.reject(new BridgeError({ code: "command_unknown", outcome: "unknown" }));
    }
    this.pending.clear();
    this.observations.clear();
    this.publish({
      connected: false,
      bridgePhase,
      blackoutPending: false,
      simulation: {},
      selecting: false,
      shown: {},
      live: {},
      running: {},
      running_meta: {},
      values_meta: {},
      history: this.staleHistory(),
      actionHistory: [],
      sceneSlot: null,
      dimSent: null,
      masterEvidence: {...this.state.masterEvidence, quality: this.state.masterEvidence.value == null ? "unknown" : "last"},
      master: this.state.master,
      feedback: null,
      status: null,
    });
  }
  receive(message) {
    const oldStatus = this.state.status;
    const context = this.context;
    if (message.status?.blackout_epoch < oldStatus?.blackout_epoch) return;
    if (message.config) {
      const [instance, revision] = (message.config.revision || "").split(":");
      const [oldInstance, oldRevision] = (this.state.config?.revision || "").split(":");
      if (instance === oldInstance && Number(revision) < Number(oldRevision)) return;
    }
    const localPlanChanged = message.config && this.state.config &&
      message.config.show !== this.state.config.show;
    if (localPlanChanged) {
      for (const [id, p] of this.pending) {
        if (!p.planBound) continue;
        clearTimeout(p.timer);
        this.pending.delete(id);
        p.reject(new PlanChangedError());
      }
      this.receipts = { values_meta: new Map(), running_meta: new Map() };
    }
    const patch = localPlanChanged
      ? { running: {}, running_meta: {}, feedback: null, error: null, simulation: {}, sceneSlot: null }
      : {};
    if (message.simulation && this.state.status?.mock === true)
      patch.simulation = message.simulation;
    if (Array.isArray(message.history))
      patch.actionHistory = message.history;
    if (message.scene_slot && typeof message.scene_slot === "object")
      patch.sceneSlot = message.scene_slot;
    if (message.status) {
      const prev = this.state.status,
        s = message.status;
      patch.status = s;
      if (
        prev &&
        (prev.blackout_epoch !== s.blackout_epoch ||
          deskName(prev) !== deskName(s) ||
          deskOnline(prev) && !deskOnline(s))
      ) {
        this.context++;
        this.selectionSerial++;
        const switchedShow = Boolean(deskName(prev) && deskName(s) && deskName(prev) !== deskName(s));
        this.needsSelectionSync = !switchedShow && this.state.selected.length > 0;
        this.selectionSyncPromise = null;
        Object.assign(patch, {
          simulation: {},
          ...(switchedShow ? { selected: [] } : {}),
          selecting: false,
          live: {},
          shown: {},
          running: {},
          running_meta: {},
          values_meta: {},
          master: null,
          sceneSlot: null,
        });
      }
    }
    if (message.config) {
      const old = this.state.config;
      const showSwitched = Boolean(old && old.show !== message.config.show);
      const fixturesChanged = Boolean(
        old &&
          JSON.stringify(
            old.fixtures?.map((f) => [f.id, f.type, f.address, f.missing]),
          ) !==
            JSON.stringify(
              message.config.fixtures?.map((f) => [
                f.id,
                f.type,
                f.address,
                f.missing,
              ]),
            ),
      );
      if (showSwitched || fixturesChanged) {
        this.context++;
        this.selectionSerial++;
        const validIds = new Set(
          (message.config.fixtures || []).filter((f) => !f.missing).map((f) => f.id),
        );
        const currentSelected = patch.selected ?? this.state.selected;
        const nextSelected = showSwitched
          ? []
          : currentSelected.filter((id) => validIds.has(id));
        this.needsSelectionSync = nextSelected.length > 0;
        this.selectionSyncPromise = null;
        Object.assign(patch, {
          selected: nextSelected,
          selecting: false,
          shown: {},
          live: {},
          values_meta: {},
        });
      }
      patch.config = message.config;
    }
    if (
      message.values_revision === undefined ||
      message.values_revision > (this.valuesRevision ?? -1)
    ) {
      if (message.values_revision !== undefined)
        this.valuesRevision = message.values_revision;
      for (const key of ["shown", "live", "master", "tracked", "values_meta"])
        if (key in message) patch[key] = message[key];
    }
    for (const key of ["running", "running_meta"])
      if (message[key]) patch[key] = { ...(patch[key] ?? this.state[key]), ...message[key] };
    for (const key of ["values_meta", "running_meta"])
      if (patch[key])
        for (const [id, meta] of Object.entries(patch[key])) {
          const old = this.receipts[key].get(id);
          if (!old || old.updated_at !== meta.updated_at)
            this.receipts[key].set(id, {
              updated_at: meta.updated_at,
              at: Date.now(),
            });
        }
    const confirmedShow = deskName(message.status);
    const showChanged = (message.config && this.state.config && message.config.show !== this.state.config.show)
      || (confirmedShow && this.lastDeskShow && confirmedShow !== this.lastDeskShow);
    if (confirmedShow) this.lastDeskShow = confirmedShow;
    const patchChanged = message.config && this.state.config && JSON.stringify(this.state.config.fixtures?.map(f=>[f.id,f.type,f.address])) !== JSON.stringify(message.config.fixtures?.map(f=>[f.id,f.type,f.address]));
    if (showChanged || patchChanged) {
      this.observations.clear();
      patch.history = {};
      patch.masterEvidence = {quality:"unknown"};
      if (showChanged) {
        this.needsSelectionSync = false;
        this.selectionSyncPromise = null;
        patch.selected = [];
        patch.selecting = false;
      }
    } else patch.history = this.staleHistory(false);
    const merged = {...this.state,...patch};
    const online = deskOnline(merged.status);
    const readback = patch.values_meta?.live;
    if (readback?.source === "ma2" && Number.isFinite(readback.updated_at))
      this.lastReadbackAt = Math.max(this.lastReadbackAt, readback.updated_at);
    if (this.context !== context) {
      // Ignore cached dimmer samples when the desk, plan or selection context is invalidated.
      this.dimReadbackFloor = this.lastReadbackAt;
      patch.dimSent = null;
      for (const attrs of Object.values(patch.history))
        if (attrs.dim?.quality === "confirmed") attrs.dim.quality = "last";
    }
    if (!online && !showChanged && !patchChanged) patch.history = this.staleHistory();
    if (patch.values_meta) for (const [id,attrs] of Object.entries(patch.history))
      for (const [key,entry] of Object.entries(attrs)) {
        const freshLive = online && patch.values_meta.live?.freshness === "fresh" && patch.values_meta.live.source === "ma2" && (patch.live || this.state.live)?.[id]?.[key] != null;
        const freshSent = online && patch.values_meta[`sent:${id}:${key}`]?.freshness === "fresh";
        if (!freshLive && !freshSent && entry.quality !== "pending") patch.history[id] = {...patch.history[id], [key]:{...entry,quality:entry.quality === "unconfirmed" ? "unconfirmed" : "last"}};
      }
    // Only observations in this message can create new evidence, never cached React state.
    for (const [id, attrs] of Object.entries(patch.shown || {})) {
      for (const [key,value] of Object.entries(attrs)) {
        const meta = merged.values_meta?.[`sent:${id}:${key}`];
        if (!meta || !this.newObservation(`sent:${id}:${key}`,meta,value)) continue;
        if (patch.history[id]?.[key]?.intent === "jog") continue;
        const prevEntry = patch.history[id]?.[key];
        patch.history[id] = {...patch.history[id], [key]: {value, quality:online && meta.freshness === "fresh" ? "pending" : "unconfirmed",sentAt:prevEntry?.sentAt ?? Date.now(),basisAt:Date.now(),intent:"absolute",requestId:prevEntry?.requestId,ackAt:prevEntry?.ackAt,ackReadbackAt:prevEntry?.ackReadbackAt}};
      }
    }
    if (patch.live && merged.values_meta?.live?.source === "ma2") {
      const liveMeta = merged.values_meta.live;
      for (const [id,attrs] of Object.entries(patch.live))
        for (const [key,value] of Object.entries(attrs)) {
          if (key === "dim" && !(liveMeta.updated_at > this.dimReadbackFloor)) continue;
          const cur = patch.history[id]?.[key];
          if (cur?.quality === "pending") {
            const at = this.receipts.values_meta.get("live")?.at ?? 0;
            if (!online || liveMeta.freshness !== "fresh" || Date.now() - at > 6000) continue;
            // Ignore readback captured before our in-flight command was ACKed.
            if (cur.requestId && this.pending.has(cur.requestId)) continue;
            if (Number.isFinite(cur.ackReadbackAt) && !(liveMeta.updated_at > cur.ackReadbackAt)) continue;
            // Short grace window after ACK for dim/rgb so an already-in-flight pre-command DMX sample cannot bounce the slider back.
            if ((key === "dim" || key === "rgb") && Date.now() - (cur.ackAt ?? cur.sentAt ?? 0) < 1800) {
              const matches = key === "dim"
                ? typeof value === "number" && typeof cur.value === "number" && Math.abs(value - cur.value) <= 1.5
                : Array.isArray(value) && Array.isArray(cur.value) && value.length === 3 &&
                  value.every((c, i) => Math.abs(c - cur.value[i]) <= 2);
              if (!matches) continue;
            }
          }
          if (!this.newObservation(`live:${id}:${key}`, liveMeta, value)) continue;
          const at=this.receipts.values_meta.get("live")?.at ?? 0;
          patch.history[id] = {...patch.history[id], [key]: {value, quality:online && liveMeta.freshness === "fresh" && Date.now()-at<=6000 ? "confirmed" : "last",confirmedAt:at}};
        }
    }
    const masterMeta = merged.values_meta?.master;
    if (typeof patch.master === "number" && this.newObservation("master",masterMeta,patch.master)) patch.masterEvidence = {value:patch.master, quality:online && masterMeta?.freshness === "fresh" ? (masterMeta.source === "ma2" ? "confirmed" : "pending") : "last"};
    else if (!showChanged && !patchChanged) patch.masterEvidence = {...this.state.masterEvidence, quality:(!online || ("master" in patch && patch.master == null) || (patch.values_meta && masterMeta?.freshness !== "fresh")) && this.state.masterEvidence.value != null ? "last" : this.state.masterEvidence.quality};
    this.publish(patch);
    if ("ok" in message) {
      const p = this.pending.get(message.request_id);
      if (!p) return;
      clearTimeout(p.timer);
      this.pending.delete(message.request_id);
      if (p.a === "blackout") this.publish({ blackoutPending: false });
      const uncertain =
        ["unknown", "partial", "failed"].includes(message.outcome) ||
        (message.command_evidence || []).some((v) => v !== "sent");
      if (p.a === "scene_go") {
        if (Array.isArray(message.skipped_off) && message.skipped_off.length) {
          this.publish({ skippedOff: message.skipped_off });
        } else if (message.ok && !uncertain) {
          this.publish({ skippedOff: [] });
        }
      }
      if (!message.ok || uncertain) this.invalidateRequest(message.request_id);
      else this.markAckedRequest(message.request_id);
      if (!message.ok || uncertain) {
        const code = message.code ?? message.reason?.code ?? (message.conflict ? "plan_revision" : undefined) ??
          (message.outcome === "unknown" || (message.command_evidence || []).includes("unknown") ? "command_unknown"
            : message.outcome === "partial" ? "command_partial" : undefined);
        const error = new BridgeError({ ...message, code });
        this.publish({ error, feedback: null });
        p.reject(error);
      } else {
        if (["plan_editing", "edit_begin", "edit_end", "highlight_ping"].includes(p.a)) {
          p.resolve(message);
          return;
        }
        this.publish({
          feedback: {
            a: message.a,
            text: "Обработка мостом завершена; состояние — по readback",
          },
          error: null,
        });
        p.resolve(message);
      }
    }
  }
  action(action) {
    const blocked = this.blockReason(action.a);
    if (blocked) return Promise.reject(new BridgeError(blocked));
    const request = {
      ...action,
      request_id: `${this.prefix}:${++this.serial}`,
      config_revision: action.config_revision ?? this.state.config?.revision,
      blackout_epoch: this.state.status.blackout_epoch,
    };
    const categories = this.state.status.readiness?.actions;
    const planBound = !["show_open_plan", "show_bind"].includes(action.a) &&
      (Object.hasOwn(categories?.light || {}, action.a) ||
        Object.hasOwn(categories?.plan || {}, action.a) || ["clear", "undo"].includes(action.a));
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(request.request_id);
        this.invalidateRequest(request.request_id);
        if (action.a === "blackout") this.publish({ blackoutPending: false });
        const error = new BridgeError({ code: "command_unknown", outcome: "unknown" });
        this.publish({ error });
        reject(error);
      }, 45000);
      this.pending.set(request.request_id, {
        a: action.a,
        planBound,
        resolve,
        reject,
        timer,
      });
      if (action.a === "blackout") this.publish({ blackoutPending: true });
      try {
        this.socket.send(JSON.stringify(request));
        const keys = {dim:["dim"],color:["rgb"],aim:["pan","tilt"],jog:["pan","tilt"],zoom:["zoom"],focus:["focus"],strobe:["strobe"]}[action.a];
        if (action.a === "master") this.publish({masterEvidence:{value:action.v,quality:"pending"}});
        if (keys) {
          const history = this.staleHistory(false);
          for (const id of this.state.selected) for (const key of keys) {
            let value = key === "rgb" ? [action.r,action.g,action.b] : action[key] ?? action.v;
            if (action.a === "jog") {
              const prior=history[id]?.[key],spec=this.state.config?.attrs?.[key];
              const f=this.state.config?.fixtures?.find(f=>f.id===id);
              let delta=Math.round(action[key]*100)/100;
              if (!delta) continue;
              // Match backend per-fixture inversion and optional mirror, without constructing MA2 commands.
              const ordered=this.state.config.fixtures.filter(f=>this.state.selected.includes(f.id)).sort((a,b)=>(a.x??.5)-(b.x??.5)||a.id-b.id);
              const mirror=key==="pan" && action.mirror===true && ordered.slice(0,Math.floor(ordered.length/2)).some(f=>f.id===id);
              if ((f?.[`flip_${key}`]===true) !== mirror) delta=-delta;
              if (!spec || !(spec.max > spec.min)) continue;
              const base = typeof prior?.value === "number" ? prior.value : 50;
              value=Math.max(0,Math.min(100,base+delta*100/(spec.max-spec.min)));
            }
            if (action.a === "aim" && action[key] != null) {
              const spec = this.state.config.attrs?.[key];
              value = spec ? (action[key]-spec.min)/(spec.max-spec.min)*100 : undefined;
            }
            if (value !== undefined) history[id] = {...history[id],[key]:{value,quality:"pending",sentAt:Date.now(),basisAt:action.a === "jog" ? (history[id]?.[key]?.basisAt ?? Date.now()) : Date.now(),requestId:request.request_id,intent:action.a === "jog" ? "jog" : "absolute",confirmedAt:action.a === "jog" ? history[id]?.[key]?.confirmedAt : undefined}};
          }
          const dimSent = action.a === "dim"
            ? { value: action.v, selectionSerial: this.selectionSerial }
            : this.state.dimSent;
          this.publish({history, dimSent});
        }
      } catch (e) {
        clearTimeout(timer);
        this.pending.delete(request.request_id);
        this.invalidateRequest(request.request_id);
        if (action.a === "blackout") this.publish({ blackoutPending: false });
        reject(e);
      }
    });
  }
  forgetSelection() {
    ++this.selectionSerial;
    this.needsSelectionSync = false;
    this.selectionSyncPromise = null;
    this.publish({ selected: [], selecting: false });
  }
  async syncSelection(ids = this.state.selected, serial = this.selectionSerial) {
    const a = ids.length ? "select_fixtures" : "clear";
    const request = this.action(ids.length ? { a, ids } : { a });
    this.selectionSyncPromise = request;
    try {
      await request;
      if (serial === this.selectionSerial) this.needsSelectionSync = false;
    } catch (e) {
      if (serial === this.selectionSerial) this.needsSelectionSync = true;
      throw e;
    } finally {
      if (this.selectionSyncPromise === request) this.selectionSyncPromise = null;
    }
  }
  async select(ids) {
    const fixtures = this.state.config?.fixtures;
    const next = [...new Set(ids)].filter(
      (id) => !fixtures || fixtures.some((f) => f.id === id && !f.missing),
    );
    const serial = ++this.selectionSerial;
    this.selectionSyncPromise = null;
    const a = next.length ? "select_fixtures" : "clear";
    const blocked = this.blockReason(a);
    this.needsSelectionSync = blocked !== null;
    this.publish({ selected: next, selecting: false });
    if (blocked) return;
    await this.syncSelection(next, serial);
  }
  async control(action) {
    const blocked = this.blockReason(action.a);
    if (blocked) throw new BridgeError(blocked);
    if (!this.state.selected.length)
      throw new BridgeError(issue("selection_pending"));
    if (this.selectionSyncPromise) {
      await this.selectionSyncPromise;
    }
    if (this.needsSelectionSync) {
      await this.syncSelection(this.state.selected, this.selectionSerial);
    }
    return this.action(action);
  }
  expireEvidence(now = Date.now()) {
    const patch = {};
    for (const key of ["values_meta", "running_meta"]) {
      let changed = false;
      const next = { ...this.state[key] };
      for (const [id, meta] of Object.entries(next))
        if (
          meta.freshness === "fresh" &&
          now - (this.receipts[key].get(id)?.at ?? now) > 6000
        ) {
          next[id] = { ...meta, freshness: "stale" };
          changed = true;
        }
      if (changed) patch[key] = next;
    }
    const history=this.staleHistory(false);
    let expired=false;
    for(const attrs of Object.values(history)) for(const entry of Object.values(attrs)) {
      if(entry.quality==="confirmed" && now-(entry.confirmedAt??now)>6000){entry.quality="last";expired=true;}
      if(entry.quality==="pending" && now-(entry.sentAt??now)>6000){entry.quality="unconfirmed";expired=true;}
    }
    if (Object.keys(patch).length || expired) {
      patch.history = history;
      patch.masterEvidence = {...this.state.masterEvidence, quality:this.state.masterEvidence.value == null ? "unknown" : "last"};
      this.publish(patch);
    }
  }
  newObservation(key,meta,value) {
    const token = JSON.stringify([meta?.updated_at ?? null,value]);
    const old=this.observations.get(key);
    if (old?.token === token || (meta?.updated_at != null && old?.updated_at != null && meta.updated_at < old.updated_at)) return false;
    this.observations.set(key,{token,updated_at:meta?.updated_at});
    return true;
  }
  staleHistory(stale = true) {
    return Object.fromEntries(Object.entries(this.state.history || {}).map(([id,attrs]) => [id,
      Object.fromEntries(Object.entries(attrs).map(([key,entry]) => [key,{...entry, quality:stale ? (["pending","unconfirmed"].includes(entry.quality) ? "unconfirmed" : "last") : entry.quality}]))]));
  }
  markAckedRequest(requestId) {
    const history = this.staleHistory(false);
    let changed = false;
    const ackAt = Date.now();
    const ackReadbackAt = this.lastReadbackAt;
    for (const attrs of Object.values(history))
      for (const entry of Object.values(attrs))
        if (entry.requestId === requestId && entry.quality === "pending") {
          entry.ackAt = ackAt;
          entry.ackReadbackAt = ackReadbackAt;
          changed = true;
        }
    if (changed) this.publish({ history });
  }
  invalidateRequest(requestId) {
    const history=this.staleHistory(false);
    for(const attrs of Object.values(history)) for(const entry of Object.values(attrs))
      if(entry.requestId===requestId && entry.quality==="pending") entry.quality="unconfirmed";
    this.publish({history});
  }
  report(error) {
    if (error instanceof PlanChangedError) return;
    this.publish({ error: error instanceof BridgeError ? error : new BridgeError(error) });
  }
}
export const bridge = new BridgeClient();
