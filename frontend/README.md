# PageIndex frontend

[![Next.js 16](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs)](package.json)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](package.json)
[![Tailwind CSS 4](https://img.shields.io/badge/Tailwind_CSS-4-06B6D4?logo=tailwindcss&logoColor=white)](app/globals.css)

Next.js provides the PDF library, citation-backed chat, search, and extraction UI. Shared components use [Atlassian design foundations](https://atlassian.design/design-system) and the [Rovo generation pattern](https://atlassian.design/rovo-ui/generative-border).

## Run locally

Use Node.js 20.19+ in the 20.x series, or Node.js 22.12+ and start the [backend](../backend/README.md) first.

```bash
npm ci
npm run dev
```

Open [PageIndex](http://localhost:3000). The frontend proxies API requests to `http://127.0.0.1:8000` during native development. Set `PAGEINDEX_BACKEND_URL` in the shell before starting Next.js to override the address, or set `PAGEINDEX_PROXY_BODY_LIMIT_MB` to adjust the proxy limit (202 MiB by default). Docker Compose uses its internal backend address. [Docker setup](../README.md#run-with-docker)

Use `npm run format` for Oxfmt and `npm run lint` for Oxlint. Run `npm run typecheck` and `npm run build` to verify changes.

## Sign-in

The public homepage at `/` links to the workspace, sign-in, and registration. With authentication enabled, the sign-in and registration pages show the methods configured for the app. The **Account** menu opens **Profile & settings** at `/account`, where signed-in users manage recovery email, connected sign-in methods, provider settings, and sessions. [Backend authentication setup](../backend/README.md#authentication)

## Using the workspace

- In **Profile & settings**, upload, replace, or remove a profile photo. The account menu shows your name and photo, with initials when no photo is saved.

- In **Provider settings**, save a PageIndex API key for PDF features and a chat provider, API key, and model for answers.
- In **Documents**, choose a collection in the upload dialog. Use the **⋯** menu to move a PDF between collections, rename it, or retry a failed upload. Moving preserves the existing PDF index and citations. Select multiple PDFs to move or trash them together. Deleting a collection sends it and its PDFs to Trash. Open the collection in Trash to restore individual PDFs, or restore the collection to recover the PDFs deleted with it.
- In **Chat**, choose a library, collection, or single PDF. Ask “List the documents and their total pages” to get a table for the selected scope without using model tokens. Use **Older** and **Newer** in conversation history to browse saved chats.
