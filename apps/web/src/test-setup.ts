import "@testing-library/jest-dom/vitest";

import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";

// Testing Library only cleans up automatically when Vitest globals are enabled.
afterEach(cleanup);

// The app frame draws icons and a dashboard; on a loaded CI machine the first
// render of a file can take over the library's default second.
configure({ asyncUtilTimeout: 3000 });
