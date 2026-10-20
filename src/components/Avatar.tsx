import { useEffect, useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent, KeyboardEvent as ReactKeyboardEvent } from 'react';
import { avatarUrl } from '../lib/avatars';
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
  const avatarId = useAppStore((s) => s.avatarId);
  const setPosition = useAppStore((s) => s.setPosition);
  const openChat = useAppStore((s) => s.openChat);
  const openSettings = useAppStore((s) => s.openSettings);
  const [viewport, setViewport] = useState(() => ({ width: window.innerWidth, height: window.innerHeight }));
  // Во время перетаскивания позиция живёт локально и попадает в стор (и localStorage) один раз, в конце.
  const [dragPosition, setDragPosition] = useState<Point | null>(null);
  const drag = useRef<Drag | null>(null);
  const dragging = dragPosition !== null;
  // На телефоне аватар не должен закрывать собой всю страницу.
  const maxForViewport = viewport.width < 600 ? viewport.width * 0.6 : viewport.width - 16;
  const visualSize = Math.round(Math.min(size, Math.max(120, maxForViewport), Math.max(120, viewport.height - 16)));
  const actualPosition = boundPosition(
    dragPosition ?? position ?? startingPosition(visualSize, viewport.width, viewport.height),
    visualSize,
    viewport.width,
    viewport.height,
  );

  useEffect(() => {
    const onResize = () => setViewport({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  function onPointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    // Ctrl+клик на macOS — это правый клик: его обрабатывает onContextMenu.
    if (event.button !== 0 || event.ctrlKey) return;
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
    setDragPosition(boundPosition(
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
    if (start.moved && dragPosition) setPosition(dragPosition);
    setDragPosition(null);
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
        // Долгое нажатие на тачскрине тоже вызывает contextmenu: не даём последующему pointerup открыть чат.
        drag.current = null;
        setDragPosition(null);
        openSettings({ x: event.clientX, y: event.clientY });
      }}
      onKeyDown={onKeyboard}
    >
      <img src={avatarUrl(avatarId)} alt="" draggable={false} />
      {!dragging && <span className="avatar__aura" aria-hidden="true" />}
    </div>
  );
}
