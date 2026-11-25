import { useEffect, useRef } from "react";
import { bridge } from "./client.mjs";
import { blackoutKey, supports } from "./model.mjs";
const layerSelector = 'dialog[open], details[data-shortcut-layer][open], [data-shortcut-layer]:not(details)';
const editingSelector = 'input, textarea, select, iframe, details[open], [role="textbox"], [role="combobox"], [role="listbox"], [role="slider"], [role="spinbutton"], [role="separator"]';
const ownsFocus = target => target?.isContentEditable || target?.closest?.(editingSelector);

export default function useHotkeys(options) {
  const latest = useRef(options);
  latest.current = options;
  const armed = useRef(null),
    armTimer = useRef(null),
    keys = useRef(new Set()),
    jogPending = useRef(false);
  const { state, enabled = true } = options;
  const jogBlocked = bridge.blockReason("jog")?.code;
  const blackoutBlocked = bridge.blockReason("blackout")?.code;
  useEffect(() => {
    armed.current = null;
    latest.current.onArm(false);
    clearTimeout(armTimer.current);
    keys.current.clear();
  }, [
    state.status?.blackout_epoch,
    state.status?.ma2,
    state.status?.readiness?.show?.name,
    state.selected.join(","),
    jogBlocked,
    blackoutBlocked,
    enabled,
  ]);
  useEffect(() => {
    const clear = () => {
      keys.current.clear();
      armed.current = null;
      latest.current.onArm(false);
      clearTimeout(armTimer.current);
    };
    // Keep opening order for non-modal layers, even when their DOM order differs.
    let layers = [];
    function syncLayers() {
      const visible = [...document.querySelectorAll(layerSelector)];
      const opened = visible.filter(layer => !layers.includes(layer));
      layers = [...layers.filter(layer => visible.includes(layer)), ...opened];
      if (opened.length) clear();
      // Native dialogs and precise fixture selection take precedence over the scene shelf.
      return layers.findLast(layer => layer.matches("dialog")) ||
        layers.findLast(layer => layer.dataset.shortcutLayer === "local-area") ||
        layers.at(-1);
    }
    const observer = new MutationObserver(syncLayers);
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["open", "data-shortcut-layer"],
    });
    const unavailable = () => !latest.current.enabled || document.hidden || !document.hasFocus();
    const act = (a) => bridge.action(a).catch((e) => bridge.report(e));

    function down(e) {
      const layer = syncLayers();
      if (e.defaultPrevented || document.hidden || !document.hasFocus()) return;
      if (e.isComposing || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.repeat) {
        if ((e.key === "Escape" && (layer || latest.current.enabled)) || keys.current.has(e.key)) {
          e.preventDefault();
        }
        return;
      }
      if (layer) {
        if (e.key === "Escape" && !layer.matches("dialog")) {
          e.preventDefault();
          clear();
          if (layer.matches("details")) {
            layer.open = false;
            layer.querySelector("summary")?.focus();
          } else {
            const dismiss = layer.querySelector("[data-shortcut-dismiss]");
            dismiss?.focus();
            dismiss?.click();
          }
        }
        return;
      }
      if (unavailable() || ownsFocus(e.target)) return;
      const { state, onArm, onHelp, slots, invalidSlots } = latest.current;
      if (e.key === "Escape") {
        e.preventDefault();
        clear();
        bridge.select([]).catch((e) => bridge.report(e));
        return;
      }
      if (e.key === "?" || (e.code === "Slash" && e.shiftKey)) {
        e.preventDefault();
        onHelp();
        return;
      }
      if (e.code === "KeyB") {
        e.preventDefault();
        const reason = bridge.blockReason("blackout");
        if (reason) {
          bridge.report(reason);
          return;
        }
        const phase = state.status?.blackout?.phase;
        const result = blackoutKey(phase, armed.current, performance.now());
        armed.current = result.armedAt;
        onArm(result.armedAt !== null);
        clearTimeout(armTimer.current);
        if (result.send) act({ a: "blackout" });
        else
          armTimer.current = setTimeout(() => {
            armed.current = null;
            latest.current.onArm(false);
          }, 600);
      }
      if (/^[1-9]$/.test(e.key)) {
        const index = Number(e.key) - 1;
        const scene = slots[index];
        if (scene) {
          e.preventDefault();
          act({ a: "scene_go", id: scene.id, scene_identity: scene.identity, config_revision: state.config.revision });
        } else if (invalidSlots[index]) {
          e.preventDefault();
          bridge.report({ code: "scene_shortcut_unverified" });
        }
      }
      if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) {
        e.preventDefault();
        const reason = bridge.blockReason("jog");
        if (reason) {
          bridge.report(reason);
          return;
        }
        keys.current.add(e.key);
      }
    }
    function up(e) {
      keys.current.delete(e.key);
    }
    function focusChanged(e) {
      if (ownsFocus(e.target)) clear();
    }
    const interval = setInterval(async () => {
      const { state, step, movementEnabled } = latest.current;
      if (
        !movementEnabled ||
        !keys.current.size ||
        unavailable() ||
        syncLayers() ||
        ownsFocus(document.activeElement) ||
        !bridge.ready("jog") ||
        state.selecting ||
        jogPending.current
      )
        return;
      const fixtures =
        state.config?.fixtures?.filter((f) => state.selected.includes(f.id)) ||
        [];
      if (
        !fixtures.length ||
        !fixtures.every((f) => supports(f, "pos", state.config))
      )
        return;
      const pan =
          (Number(keys.current.has("ArrowRight")) -
            Number(keys.current.has("ArrowLeft"))) *
          step,
        tilt =
          (Number(keys.current.has("ArrowUp")) -
            Number(keys.current.has("ArrowDown"))) *
          step;
      if (!pan && !tilt) return;
      jogPending.current = true;
      try {
        await bridge.control({ a: "jog", pan, tilt });
      } catch (e) {
        bridge.report(e);
        keys.current.clear();
      } finally {
        jogPending.current = false;
      }
    }, 100);
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up, true);
    document.addEventListener("focusin", focusChanged);
    window.addEventListener("blur", clear);
    document.addEventListener("visibilitychange", clear);
    return () => {
      observer.disconnect();
      clearInterval(interval);
      clearTimeout(armTimer.current);
      keys.current.clear();
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up, true);
      document.removeEventListener("focusin", focusChanged);
      window.removeEventListener("blur", clear);
      document.removeEventListener("visibilitychange", clear);
    };
  }, []);
}
