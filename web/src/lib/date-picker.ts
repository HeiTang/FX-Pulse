export function mountDatePicker(input: HTMLInputElement, dates: string[]) {
  const trigger = document.querySelector<HTMLButtonElement>('#date-trigger')!;
  const panel = document.querySelector<HTMLElement>('#date-picker')!;
  const grid = document.querySelector<HTMLElement>('#calendar-days')!;
  const title = document.querySelector<HTMLElement>('#calendar-month')!;
  const display = document.querySelector<HTMLElement>('#date-display')!;
  const available = new Set(dates);
  if (!dates.length) {
    trigger.disabled = true;
    display.textContent = '無可用日期';
    return;
  }
  const firstMonth = dates[0].slice(0, 7);
  const lastMonth = dates.at(-1)!.slice(0, 7);
  let month = input.value.slice(0, 7);
  const iso = (date: Date) => date.toISOString().slice(0, 10);
  const parse = (value: string) => new Date(`${value}T00:00:00Z`);

  function close(returnFocus = false) {
    panel.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
    if (returnFocus) trigger.focus();
  }

  function render(focusDate?: string) {
    const first = parse(`${month}-01`);
    title.textContent = `${first.getUTCFullYear()} 年 ${first.getUTCMonth() + 1} 月`;
    panel
      .querySelectorAll<HTMLButtonElement>('[data-month-step]')
      .forEach((button) => {
        button.disabled =
          Number(button.dataset.monthStep) < 0
            ? month <= firstMonth
            : month >= lastMonth;
      });
    grid.replaceChildren();
    const start = new Date(first);
    start.setUTCDate(1 - first.getUTCDay());
    const focus =
      focusDate ??
      (input.value.startsWith(month)
        ? input.value
        : dates.find((date) => date.startsWith(month)));
    for (let offset = 0; offset < 42; offset++) {
      const date = new Date(start);
      date.setUTCDate(start.getUTCDate() + offset);
      const value = iso(date);
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = String(date.getUTCDate());
      button.dataset.date = value;
      button.dataset.outside = String(!value.startsWith(month));
      button.disabled = !available.has(value);
      button.tabIndex = value === focus ? 0 : -1;
      button.setAttribute(
        'aria-label',
        `${value}${button.disabled ? '，無資料' : ''}`,
      );
      button.setAttribute('aria-pressed', String(value === input.value));
      grid.append(button);
    }
    if (focusDate)
      grid
        .querySelector<HTMLButtonElement>(`[data-date="${focusDate}"]`)
        ?.focus();
  }

  trigger.addEventListener('click', () => {
    if (!panel.hidden) return close();
    month = input.value.slice(0, 7);
    render();
    panel.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    grid.querySelector<HTMLButtonElement>('[tabindex="0"]')?.focus();
    panel.scrollIntoView({ block: 'nearest' });
  });
  panel
    .querySelectorAll<HTMLButtonElement>('[data-month-step]')
    .forEach((button) =>
      button.addEventListener('click', () => {
        const date = parse(`${month}-01`);
        date.setUTCMonth(date.getUTCMonth() + Number(button.dataset.monthStep));
        month = iso(date).slice(0, 7);
        render();
      }),
    );
  grid.addEventListener('click', (event) => {
    const button = (event.target as HTMLElement).closest<HTMLButtonElement>(
      '[data-date]',
    );
    if (!button || button.disabled) return;
    input.value = button.dataset.date!;
    input.dispatchEvent(new Event('change', { bubbles: true }));
    close(true);
  });
  grid.addEventListener('keydown', (event) => {
    const step = (
      { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 } as Record<
        string,
        number
      >
    )[event.key];
    if (!step) return;
    event.preventDefault();
    const button = (event.target as HTMLElement).closest<HTMLButtonElement>(
      '[data-date]',
    );
    if (!button) return;
    const date = parse(button.dataset.date!);
    date.setUTCDate(date.getUTCDate() + step);
    const value = iso(date);
    if (!available.has(value)) return;
    month = value.slice(0, 7);
    render(value);
  });
  document.addEventListener('keydown', (event) => {
    if (panel.hidden) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      close(true);
    }
  });
  document.addEventListener('pointerdown', (event) => {
    if (!panel.hidden && !panel.parentElement!.contains(event.target as Node))
      close();
  });
  document.addEventListener('focusin', (event) => {
    if (!panel.hidden && !panel.parentElement!.contains(event.target as Node))
      close();
  });
  input.addEventListener('change', () => {
    if (available.has(input.value))
      display.textContent = input.value.replaceAll('-', '/');
  });
}
