// Catalog typing. `Messages` mirrors the English catalog's shape with every leaf widened to string;
// `MessageKey` is the union of every dotted leaf path ("student.today.start", ...). Both are derived,
// so adding a key is a one-place change in `en.ts` that the compiler then demands in every locale.
import type { en } from "./en";

export type Catalog<T> = { [K in keyof T]: T[K] extends string ? string : Catalog<T[K]> };

export type Messages = Catalog<typeof en>;

type Paths<T> = {
  [K in keyof T & string]: T[K] extends string ? K : `${K}.${Paths<T[K]>}`;
}[keyof T & string];

export type MessageKey = Paths<Messages>;
