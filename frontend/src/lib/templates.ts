import type { Language } from "../types";

export const starterTemplates: Record<Language, string> = {
  python: `def greet(name: str) -> None:
    print(f"Hello, {name}")


if __name__ == "__main__":
    greet("collaborators")
`,
  javascript: `function greet(name) {
  console.log(\`Hello, \${name}\`);
}

greet("collaborators");
`,
  cpp: `#include <iostream>
#include <string>

int main() {
  std::cout << "Hello, collaborators" << std::endl;
  return 0;
}
`,
};

export function defaultFileNameForLanguage(language: Language): string {
  if (language === "python") {
    return "main.py";
  }
  if (language === "javascript") {
    return "index.js";
  }
  return "main.cpp";
}
