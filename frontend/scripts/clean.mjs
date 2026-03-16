#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function isIgnorableRemovalError(error) {
	return (
		error &&
		typeof error === "object" &&
		("code" in error) &&
		(error.code === "ENOENT" || error.code === "EACCES" || error.code === "EPERM")
	);
}

export function cleanTargets(
	targets,
	options = {},
) {
	const rmSync =
		options.rmSync ||
		((target) => {
			fs.rmSync(target, { recursive: true, force: true });
		});
	const warn = options.warn || ((message) => console.warn(message));

	for (const target of targets) {
		try {
			rmSync(target);
		} catch (error) {
			if (!isIgnorableRemovalError(error)) {
				throw error;
			}
			if (error.code === "ENOENT") {
				continue;
			}
			warn(
				`Skipping cleanup for ${target}: ${error.code || "UNKNOWN"}${
					error.message ? ` (${error.message})` : ""
				}`,
			);
		}
	}
}

export function main() {
	cleanTargets([
		path.join(frontendDir, "dist"),
		path.join(frontendDir, "node_modules", ".vite"),
	]);
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
	main();
}
