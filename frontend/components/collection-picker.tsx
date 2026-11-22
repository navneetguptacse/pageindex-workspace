import { Field, FieldLabel } from "@/components/ui/field"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import type { Collection } from "@/lib/api"

export function CollectionPicker({
  id,
  collections,
  value,
  onChange,
  disabled,
}: {
  id: string
  collections: Collection[]
  value: string | null
  onChange: (value: string | null) => void
  disabled?: boolean
}) {
  const items = [
    { value: "none", label: "No collection" },
    ...collections.map(({ id, name }) => ({ value: id, label: name })),
  ]
  return (
    <Field>
      <FieldLabel htmlFor={id}>Collection</FieldLabel>
      <Select
        items={items}
        value={value ?? "none"}
        onValueChange={(next) => onChange(next === "none" ? null : next)}
        disabled={disabled}
      >
        <SelectTrigger id={id} className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {items.map((item) => (
            <SelectItem key={item.value} value={item.value}>
              {item.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  )
}
