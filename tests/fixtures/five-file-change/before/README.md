# Example App

A small project that exists only as test data for the diff widget. It has a frontend written in TypeScript and a
backend written in Rust, so the fixture contains files of several kinds: a README, `package.json`, build scripts and
editor configuration.

## Getting started

Install the dependencies once with `npm install`, then start the dev server with `npm run dev`. The page reloads
whenever a source file changes.

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | start the dev server with live reload |
| `npm run build` | production build into `dist` |
| `npm run typecheck` | type-check without emitting files |
| `npm test` | unit tests with `node --test` |

## Layout

| Folder | Contents |
|---|---|
| `src/frontend` | the TypeScript frontend and its build scripts |
| `src/backend` | the Rust backend |
| `test` | unit tests |
| `.zed` | editor tasks and debug configurations |

## Debugging

Start the backend and the frontend from the debug panel, in this order. If the frontend session cannot attach, start
the fallback session instead and restart it after every restart of the app.

## Releasing

Tag a commit, run `npm run build` and attach the contents of `dist` to the release.
