// UI consistency guard. One recipe per element: these rules fail the build on the drift the
// design system exists to prevent. Run with `npm run lint:ui`.
// The marketing site (src/components/landing) has its own palette and is not covered.
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

const PALETTE = "slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose";
const UTILITY = "bg|text|border|ring|fill|stroke|from|to|via|divide|outline|decoration|accent|caret|placeholder";
// A class token starts the string or follows whitespace / a variant colon.
const START = "(?:^|[\\s:\"'`])";

const CLASS_RULES = [
  {
    re: new RegExp(`\\b(?:${UTILITY})-(?:${PALETTE})-\\d{2,3}\\b`),
    message:
      "Raw Tailwind palette color. Use a token: text-destructive / bg-destructive/10, text-success, text-warning, text-beige, text-muted-foreground (THEME_TOKENS.colors).",
  },
  { re: /-\[#[0-9a-fA-F]{3,8}\]/, message: "Hex color in a class. Use a token from tailwind.config.ts." },
  {
    re: new RegExp(`${START}shadow-\\[`),
    message: "Arbitrary shadow. Use shadow-soft / shadow-medium / shadow-large, or a glass class.",
  },
  {
    re: new RegExp(`${START}(?:hover:|focus:|dark:)?(?:bg|text|border)-(?:white|black)\\b`),
    message: "Pure white/black. Use bg-card, text-foreground, text-destructive-foreground, or a glass class.",
  },
  { re: /hover:bg-beige-dark\b/, message: "Primary hover is owned by <Button>. Use it, or hover:bg-beige/90." },
  {
    re: /hover:bg-secondary\/(?:10|20|30|40|50|70|80|90)\b/,
    message: "Row hover is hover:bg-secondary/60 (THEME_TOKENS.interaction.rowHover).",
  },
  {
    re: new RegExp(`${START}animate-spin\\b`),
    message: "Use <VocifySpinner /> (components/ui/vocify-loader), not a hand-rolled spinner.",
  },
];

const uiRecipes = {
  meta: { type: "problem", schema: [] },
  create(context) {
    const check = (node, text) => {
      for (const { re, message } of CLASS_RULES) if (re.test(text)) context.report({ node, message });
    };
    return {
      Literal(node) {
        if (typeof node.value === "string") check(node, node.value);
      },
      TemplateElement(node) {
        check(node, node.value.raw);
      },
      JSXOpeningElement(node) {
        if (node.name.type === "JSXIdentifier" && node.name.name === "select") {
          context.report({ node, message: "Use the kit Select (components/ui/select), not a native <select>." });
        }
      },
      ImportDeclaration(node) {
        if (node.source.value === "@phosphor-icons/react") {
          context.report({ node, message: "One icon set: use lucide-react (strokeWidth 1.5 for the thin look)." });
        }
      },
      ImportSpecifier(node) {
        if (node.imported.name === "Loader2") {
          context.report({ node, message: "Use <VocifySpinner /> (components/ui/vocify-loader), not Loader2." });
        }
      },
    };
  },
};

export default tseslint.config(
  { ignores: ["dist", "src/components/landing/**", "src/components/ui/**", "src/lib/theme/**", "**/*.test.*"] },
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: { parser: tseslint.parser },
    linterOptions: { reportUnusedDisableDirectives: "off" },
    // Registered so existing eslint-disable comments for these rules resolve; the rules stay off here.
    plugins: { vocify: { rules: { "ui-recipes": uiRecipes } }, "react-hooks": reactHooks },
    rules: { "vocify/ui-recipes": "error" },
  },
);
