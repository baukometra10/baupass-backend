#!/usr/bin/env python3
import re

with open('worker-app.js', 'r', encoding='utf-8') as f:
    content = f.read()

# The broken part: orphan code after switchToTab() closing brace
broken = '''    const docsCard = document.getElementById("documentsCard");
    if (docsCard) docsCard.classList.remove("hidden");
  }
}

  const hashByTab = {
    home: "home",
    vacation: "urlaub",
    timesheet: "stunden",
    documents: "docs",
    actions: "aktionen"
  };
  const nextHash = hashByTab[tabName];
  if (nextHash && window.location.hash !== `#${nextHash}`) {
    history.replaceState(null, "", `#${nextHash}`);
  }

  // Scroll to top of content
  window.scrollTo(0, 0);
}'''

fixed = '''    const docsCard = document.getElementById("documentsCard");
    if (docsCard) docsCard.classList.remove("hidden");
  }

  // Update hash for browser history
  const hashByTab = {
    home: "home",
    vacation: "urlaub",
    timesheet: "stunden",
    documents: "docs",
    actions: "aktionen"
  };
  const nextHash = hashByTab[tabName];
  if (nextHash && window.location.hash !== `#${nextHash}`) {
    history.replaceState(null, "", `#${nextHash}`);
  }

  // Scroll to top of content
  window.scrollTo(0, 0);
}'''

if broken in content:
    content = content.replace(broken, fixed)
    with open('worker-app.js', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed switchToTab() function")
else:
    print("Pattern not found - file may already be fixed or structure changed")
