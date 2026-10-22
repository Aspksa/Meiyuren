/** Русское склонение: 1 связь, 2 связи, 5 связей. */
export const plural = (n: number, one: string, few: string, many: string) => {
  const tail = n % 100, last = n % 10;
  return `${n} ${tail > 10 && tail < 20 ? many : last === 1 ? one : last >= 2 && last <= 4 ? few : many}`;
};
