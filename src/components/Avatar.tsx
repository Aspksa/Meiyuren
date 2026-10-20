import { useEffect, useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent, KeyboardEvent as ReactKeyboardEvent } from 'react';
import { boundPosition, startingPosition } from '../lib/position';
import type { Point } from '../lib/position';
import { useAppStore } from '../store/useAppStore';

type Drag = {
  pointerId: number;
  mouseOrigin: Point;
  avatarOrigin: Point;
  moved: boolean;
};

export function Avatar() {
  const position = useAppStore((s) => s.position);
  const size = useAppStore((s) => s.size);
  const opacity = useAppStore((s) => s.opacity);
  const setPosition = useAppStore((s) => s.setPosition);
  const openChat = useAppStore((s) => s.openChat);
  const openSettings = useAppStore((s) => s.openSettings);
  const [viewport, setViewport] = useState(() => ({ width: window.innerWidth, height: window.innerHeight }));
  const [dragging, setDragging] = useState(false);
  const drag = useRef<Drag | null>(null);
  const visualSize = Math.min(size, Math.max(120, viewport.width - 16), Math.max(120, viewport.height - 16));
  const actualPosition = boundPosition(
    position ?? startingPosition(visualSize, viewport.width, viewport.height),
    visualSize,
    viewport.width,
    viewport.height,
  );

  useEffect(() => {
    const onResize = () => setViewport({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    if (position && (position.x !== actualPosition.x || position.y !== actualPosition.y)) {
      setPosition(actualPosition);
    }
  }, [actualPosition.x, actualPosition.y, position, setPosition]);

  function onPointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = {
      pointerId: event.pointerId,
      mouseOrigin: { x: event.clientX, y: event.clientY },
      avatarOrigin: actualPosition,
      moved: false,
    };
  }

  function onPointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    const start = drag.current;
    if (!start || start.pointerId !== event.pointerId) return;
    const dx = event.clientX - start.mouseOrigin.x;
    const dy = event.clientY - start.mouseOrigin.y;
    if (!start.moved && Math.hypot(dx, dy) < 7) return;
    start.moved = true;
    setDragging(true);
    setPosition(boundPosition(
      { x: start.avatarOrigin.x + dx, y: start.avatarOrigin.y + dy },
      visualSize,
      viewport.width,
      viewport.height,
    ));
  }

  function endPointer(event: ReactPointerEvent<HTMLDivElement>, cancelled = false) {
    const start = drag.current;
    if (!start || start.pointerId !== event.pointerId) return;
    drag.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    setDragging(false);
    if (!cancelled && !start.moved) openChat();
  }

  function onKeyboard(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      openChat();
    } else if (event.key === 'F10' && event.shiftKey) {
      event.preventDefault();
      const rect = event.currentTarget.getBoundingClientRect();
      openSettings({ x: rect.right - 10, y: rect.top + 30 });
    }
  }

  return (
    <div
      className={`avatar ${dragging ? 'avatar--dragging' : ''}`}
      role="button"
      tabIndex={0}
      aria-label="Мэйюрэн: нажмите для чата, правой кнопкой — настройки, перетащите для перемещения"
      title="ЛКМ — чат · ПКМ — настройки · Перетаскивание — переместить"
      style={{ left: actualPosition.x, top: actualPosition.y, width: visualSize, height: visualSize, opacity }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={(event) => endPointer(event)}
      onPointerCancel={(event) => endPointer(event, true)}
      onContextMenu={(event) => {
        event.preventDefault();
        openSettings({ x: event.clientX, y: event.clientY });
      }}
      onKeyDown={onKeyboard}
    >
      <img src="/assets/avatar/meiyuren.webp" alt="" draggable={false} />
      {!dragging && <span className="avatar__aura" aria-hidden="true" />}
    </div>
  );
}
