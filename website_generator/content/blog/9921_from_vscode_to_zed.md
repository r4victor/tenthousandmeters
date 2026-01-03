Title: I switched from VSCode to Zed
Date: 2026-01-03 15:30
Tags: Zed, VSCode, Python, tools
Summary: For many years VSCode has been my day-to-day IDE for everything: Python, Go, C, occasional frontend development, and what not. It was never perfect but it worked. I like using mainstream tools with minimal configuration, so it suited me perfectly. But recent VSCode developments forced me to look for an alternative. In December I switched to [Zed](https://zed.dev) completely, and I think I'm never going back.

For many years VSCode has been my day-to-day IDE for everything: Python, Go, C, occasional frontend development, and what not. It was never perfect but it worked. I like using mainstream tools with minimal configuration, so it suited me perfectly. But recent VSCode developments forced me to look for an alternative. In December I switched to [Zed](https://zed.dev) completely, and I think I'm never going back.
## VSCode no more

VSCode felt stable over the years. This changed with the AI era. Now every update there are new AI-related features that I need to figure out how to disable. Few examples. I don't use Github Copilot. My preferred AI tool is a CLI (lately Codex). So I disabled Copilot. But VSCode continued to force it on me. After one update I see ["cmd+I to continue with copilot"](https://github.com/orgs/community/discussions/147492) on every line I edit. Another update I see new inline terminal suggestions and they only interfere with my shell suggestions. There were a few other similar intrusions I don't recall now.

So my `settings.json` grew into a list of opt-outs. I could still live with that. The biggest issue for me was that VSCode became more buggy, feeling even slower, and crashing frequently – not surprising giving the pace of shipping new Copilot features.

I still think VSCode is an amazing IDE and I'm grateful to all the maintainers and the greatest extension community. There is a hope the VSCode approach to AI integration becomes less intrusive and more thoughtful, things stabilize, and VSCode "just works" again. But now it was time to look for somethings else.

I knew I didn't want to switch to JetBrains IDEs. There are powerful but feel heavy and I don't enjoy using them. Vim, Emacs, and its modern variants are on the opposite spectrum. Probably they'll work great but only after I retire and have the time to configure and learn them properly. And there was [Zed](https://zed.dev) that I didn't know much about besides it being modern and lightweight IDE written in Rust. I gave it a try.
## Zed: first impressions

In Zed I felt immediately at home coming from VSCode. The UI is similar. Zed's default keybindings are mostly the same. The biggest UX difference for me was that VSCode shows opened files (a.k.a. open editors) in the left sidebar, which I often used for navigation. In Zed there is no such panel, and the recommended approach is to navigate using file search (`Cmd+P`). There is also a way to [import VSCode settings automatically](https://zed.dev/docs/migrate/vs-code). I wanted to start fresh, so I didn't use it. The only configuration I had to do is change the font size and theme, disable inline git blame, and enable autosave.

My main impression of Zed was how fast and responsive it is compared to VSCode. I even noticed the slowness of some other tooling, which I got used to, and optimized it. Another highlight is that Zed has been stable for me without any glitches or crashes over the last two weeks. This all brings back joy of programming.

I mostly program in Python and sometimes Go. With Go, Zed worked out-of-the-box without any extra setup. With Python, it wasn't so smooth, and I had to spent half a day to get it working. Next is boring details that I wish I knew from the start.
## Making Zed work for Python

First some context. Zed is an IDE that relies on [language servers](https://langserver.org) to provide language-specific features like autocomplete, code navigation, type checking, etc. It natively supports multiple Python language servers. One is [Pyright](https://github.com/microsoft/pyright), but its capabilities as a language server are limited – it's primarily a type checker that other language servers build upon. For example, Microsoft develops [Pylance](https://github.com/microsoft/pylance-release) as a language server on top of Pyright. Pylance is the most widely used Python language server, however, it's not open source, so it cannot be used outside of VSCode. Zed uses [Basedpyright ](https://docs.basedpyright.com/latest/) as the default language server instead.

The first problem I encountered when I opened a Python project in Zed is that I saw a lot of type checker errors highlighted in the code. Apparently, Basedpyright ran in a stricter `typeCheckingMode`. For my Python projects I used to configure Pyright with `typeCheckingMode` unspecified, which defaults to `standard`. The [Zed docs say](https://zed.dev/docs/languages/python#basedpyright) that "while Basedpyright in isolation defaults to the `recommended` [type-checking mode](https://docs.basedpyright.com/latest/benefits-over-pyright/better-defaults/#typecheckingmode), Zed configures it to use the less-strict `standard` mode by default, which matches the behavior of Pyright. This confused me since I definitely saw it working in `recommended`.

I tried to specify `typeCheckingMode` explicitly in settings.json [like shown in the docs](https://zed.dev/docs/languages/python#language-server-settings):

```json
// ...
"lsp": {
    "basedpyright": {
      "settings": {
        "basedpyright.analysis": {
          "typeCheckingMode": "standard"
        }
      }
    }
  }
// ...
```

This didn't work. There were still a lot of typing errors I didn't want to check for. I figured out eventually that as long as you have `pyproject.toml` with the `[tool.pyright]` section, the Basedpyright's default `typeCheckingMode = "recommended"` is used. My solution was to set `typeCheckingMode = "standard"` in every `pyproject.toml` explicitly. The solution took me a long time – I found several Github issues related to language server settings being ignored or not working as expected, so it looked like a bug at first. Now I see it's rather intended, although not clear from the docs. The lesson: If you define `[tool.pyright]` , don't rely on Pyright defaults but set the options explicitly.

Next I noticed that I as I edited the code I didn't see new typing errors shown for a file until I changed that file. I'd like to see such errors when, for example, a symbol is deleted but still used in another file. This I fixed by [setting `"disablePullDiagnostics": true`](https://github.com/zed-industries/zed/issues/36810) in settings.json:

```json
// ...
  "lsp": {
    "basedpyright": {
      "initialization_options": {
        "disablePullDiagnostics": true
      },
    }
  }
// ...
```

That's basically it. Virtual environment detection and other Python specifics were smooth. At one point I also tried [ty](https://docs.astral.sh/ty/) instead of Basedpyright, which [announced Beta just recently](https://astral.sh/blog/ty). It worked well from the start. I still chose Basedpyright because the CI runs Pyright and I want the same type checker locally. But given the success of ruff and uv, there is a high chance of me (and everyone else) switching to ty both for development and CI.
## Wrapping up

Zed is now my go-to IDE for Python and Go and my first choice as a general-purpose editor. It's fast, stable, familiar, feature-rich, with nice out-of-the box experience. The Zed extension ecosystem is tiny compared to VSCode, but I found it sufficient for my needs. The only thing I miss is a powerful git diff viewer with side-by-side diffs like [GitLens](https://www.gitkraken.com/gitlens).

Zed's AI features are actively developed but easily ignored and don't stand in the way. Zed offers [paid plans](https://zed.dev/pricing) for edit predictions, which seems like it can be a nice way to keep the project going. I want to wish Zed all the best!

As regards to VSCode, they finally got a decent competitor, and the Microsoft leverage may not be sufficient to keep the dominant position. VSCode, wake up!

Finally, my minimal Zed's settings.json in full:

```json
{
  "autosave": "on_focus_change",
  "git": {
    "inline_blame": {
      "enabled": false
    }
  },
  "icon_theme": {
    "mode": "light",
    "light": "Zed (Default)",
    "dark": "Zed (Default)"
  },
  "base_keymap": "VSCode",
  "ui_font_size": 22,
  "buffer_font_size": 18,
  "theme": {
    "mode": "light",
    "light": "One Light",
    "dark": "One Dark"
  },
  "lsp": {
    "basedpyright": {
      "initialization_options": {
        "disablePullDiagnostics": true
      },
      "settings": {
        "basedpyright.analysis": {
          // Won't take affect if pyproject.toml has `[tool.pyright]`
          "typeCheckingMode": "standard"
        }
      }
    }
  },
  "languages": {
    "Python": {
      "language_servers": ["!ty", "basedpyright", "..."]
    }
  }
}
```
<br>

*If you have any questions, comments or suggestions, feel free to join the [GitHub discussion](https://github.com/r4victor/tenthousandmeters/discussions/5).*

<br>