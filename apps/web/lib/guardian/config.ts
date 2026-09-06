// Guardian-portal configuration.
//
// The development stub that lived here — a synthetic guardian ref and a hand-minted bearer token —
// is gone. A guardian signs in through /v1/identity and the portal reads their identity from the
// session store.

export { API_BASE } from "../session/config";
