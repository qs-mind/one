// The addresses of the new interface, after the hash: #/tender/<id>/room. Every place links through these.

/** The three first-launch steps, in order. */
export const WELCOME_STEPS = ["language", "profile", "ai"] as const;
export type WelcomeStep = (typeof WELCOME_STEPS)[number];

/** The Settings section the rail opens: the first in the list (My profile). */
export const FIRST_SETTINGS = "me";

export const paths = {
  home: "/",
  tender: (id: string) => `/tender/${id}`,
  doc: (id: string, docId: string) => `/tender/${id}/doc/${docId}`,
  room: (id: string) => `/tender/${id}/room`,
  member: (id: string, memberId: string) => `/tender/${id}/member/${memberId}`,
  settings: (section: string = FIRST_SETTINGS) => `/settings/${section}`,
  welcome: (step: WelcomeStep) => `/welcome/${step}`,
};
