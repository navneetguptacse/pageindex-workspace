export const extractionPresets: Record<
  string,
  { name: string; schema: Record<string, unknown> }
> = {
  financial: {
    name: "Financial Summary",
    schema: {
      type: "object",
      properties: {
        company_name: {
          type: "string",
          description: "Full company name as printed on report cover",
        },
        fiscal_year: {
          type: "number",
          description: "Fiscal year reported",
        },
        total_revenue_millions: {
          type: "number",
          description: "Total revenue in millions USD",
        },
        net_income_millions: {
          type: "number",
          description: "Net income in millions USD",
        },
        operating_margin_percent: {
          type: "number",
          description: "Operating margin percentage",
        },
        key_highlights: {
          type: "array",
          items: { type: "string" },
          description: "Bullet points of key performance highlights",
        },
      },
    },
  },
  invoice: {
    name: "Invoice & Billing",
    schema: {
      type: "object",
      properties: {
        vendor_name: {
          type: "string",
          description: "Name of the supplier or vendor",
        },
        invoice_number: {
          type: "string",
          description: "Invoice or reference number",
        },
        invoice_date: {
          type: "string",
          description: "Date issued in YYYY-MM-DD format",
        },
        total_amount: {
          type: "number",
          description: "Total due amount",
        },
        line_items: {
          type: "array",
          items: {
            type: "object",
            properties: {
              description: { type: "string" },
              quantity: { type: "number" },
              unit_price: { type: "number" },
              total: { type: "number" },
            },
          },
          description: "All line items in order",
        },
      },
    },
  },
  leadership: {
    name: "Leadership / People",
    schema: {
      type: "object",
      properties: {
        organization: { type: "string", description: "Organization name" },
        executives: {
          type: "array",
          items: {
            type: "object",
            properties: {
              name: { type: "string", description: "Full name" },
              title: { type: "string", description: "Official job title" },
            },
          },
          description: "Officers and board members listed",
        },
      },
    },
  },
}
