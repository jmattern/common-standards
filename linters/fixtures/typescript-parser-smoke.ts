type Box<T> = { value: T };

export function unwrap<T>(box: Box<T>): T {
  return box.value;
}
