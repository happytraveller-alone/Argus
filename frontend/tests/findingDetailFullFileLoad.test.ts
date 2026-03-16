import test from "node:test";
import assert from "node:assert/strict";

import {
  classifyFullFileLoadError,
  FULL_FILE_FAILED_MESSAGE,
  FULL_FILE_UNAVAILABLE_MESSAGE,
} from "../src/pages/finding-detail/fullFileLoad.ts";

test("classifyFullFileLoadError 将 404 归类为不可查看完整文件", () => {
  const result = classifyFullFileLoadError({
    response: {
      status: 404,
    },
  });

  assert.deepEqual(result, {
    kind: "unavailable",
    message: FULL_FILE_UNAVAILABLE_MESSAGE,
  });
});

test("classifyFullFileLoadError 将 400 归类为不可查看完整文件", () => {
  const result = classifyFullFileLoadError({
    response: {
      status: 400,
    },
  });

  assert.deepEqual(result, {
    kind: "unavailable",
    message: FULL_FILE_UNAVAILABLE_MESSAGE,
  });
});

test("classifyFullFileLoadError 将网络或服务错误归类为加载失败", () => {
  const result = classifyFullFileLoadError(new Error("Network Error"));

  assert.deepEqual(result, {
    kind: "failed",
    message: FULL_FILE_FAILED_MESSAGE,
  });
});
