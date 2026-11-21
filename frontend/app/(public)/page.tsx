import Link from "next/link"
import { ArrowRightIcon, ScanSearchIcon, Table2Icon } from "lucide-react"

import { DocumentChatCard } from "@/components/document-chat-card"
import { LegacyAuthLink } from "@/components/legacy-auth-link"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

const features = [
  {
    title: "Search your library",
    description: "Find relevant pages across a single PDF or a collection.",
    icon: ScanSearchIcon,
  },
  {
    title: "Extract structured data",
    description: "Turn fields and tables into JSON for your next step.",
    icon: Table2Icon,
  },
]

export default function HomePage() {
  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-12 sm:px-6 sm:py-20">
      <LegacyAuthLink />
      <section className="flex max-w-2xl flex-col items-start gap-5">
        <h1 className="text-4xl leading-tight font-semibold tracking-tight sm:text-5xl">
          Find answers in your PDFs
        </h1>
        <p className="max-w-xl text-base text-muted-foreground sm:text-lg">
          PageIndex brings your document library, search, chat, and extraction
          into one workspace.
        </p>
        <Button size="lg" render={<Link href="/workspace" />}>
          Open workspace <ArrowRightIcon data-icon="inline-end" />
        </Button>
      </section>
      <div className="mt-10 sm:mt-12">
        <DocumentChatCard />
      </div>
      <section
        aria-label="Workspace features"
        className="mt-3 grid gap-3 sm:grid-cols-2"
      >
        {features.map(({ title, description, icon: Icon }) => (
          <Card key={title}>
            <CardHeader>
              <Icon className="mb-1 size-5 text-primary" aria-hidden="true" />
              <CardTitle>{title}</CardTitle>
              <CardDescription>{description}</CardDescription>
            </CardHeader>
          </Card>
        ))}
      </section>
    </main>
  )
}
