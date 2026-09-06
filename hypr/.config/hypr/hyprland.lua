-- ~/.config/hypr/hyprland.lua
-- Baseline enxuta — ref.: ~/Documentos/hyprland-migration-design.md
--
-- Config em Lua: desde o Hyprland 0.55 o formato INI (hyprlang) foi descontinuado.
-- No 0.56 as window rules SÓ existem em Lua (hl.window_rule{}), por isso a config
-- inteira foi portada para cá. O KDE continua intacto como fallback.
--
-- A antiga árvore INI está em ~/.config/hypr/_legacy_ini_backup/ (só referência).
-- hyprlock.conf / hypridle.conf / hyprpaper.conf continuam em INI (projetos à parte).

local mod = "SUPER"

--------------------------------------------------------------------------------
-- ENV — NVIDIA + toolkits  (era conf.d/env.conf)
--------------------------------------------------------------------------------
-- Setado antes de o display server subir.
hl.env("LIBVA_DRIVER_NAME", "nvidia")
hl.env("__GLX_VENDOR_LIBRARY_NAME", "nvidia")
hl.env("NVD_BACKEND", "direct")

hl.env("ELECTRON_OZONE_PLATFORM_HINT", "auto")
hl.env("MOZ_ENABLE_WAYLAND", "1")
hl.env("QT_QPA_PLATFORM", "wayland;xcb")
hl.env("QT_WAYLAND_DISABLE_WINDOWDECORATION", "1")

hl.env("XCURSOR_SIZE", "24")
hl.env("HYPRCURSOR_SIZE", "24")

-- grootshell (shell Quickshell): o wrapper grootshell-ipc e o próprio shell
-- localizam a instância pelo path do checkout. Setado aqui p/ todo bind herdar.
hl.env("GROOTSHELL_CONFIG_PATH", os.getenv("HOME") .. "/.config/quickshell/grootshell")

--------------------------------------------------------------------------------
-- MONITORS  (era conf.d/monitors.conf)
--------------------------------------------------------------------------------
hl.monitor({ output = "DP-1",     mode = "1920x1080@144", position = "0x0",      scale = 1 })
hl.monitor({ output = "HDMI-A-1", mode = "1366x768@60",   position = "1920x312", scale = 1 })
-- fallback genérico para qualquer outra saída
hl.monitor({ output = "", mode = "preferred", position = "auto", scale = 1 })

--------------------------------------------------------------------------------
-- INPUT  (era conf.d/input.conf)
--------------------------------------------------------------------------------
hl.config({
    input = {
        kb_layout    = "us,br",
        kb_variant   = ",abnt2",
        -- Ctrl direito -> Super_R (Mod4): vira modificador de WM. Ctrl esquerdo fica normal.
        -- Win direito (se existir) -> Ctrl direito. A tecla Super continua valendo como mod.
        kb_options   = "grp:alt_shift_toggle,ctrl:swap_rwin_rctl",
        repeat_rate  = 40,
        repeat_delay = 300,
        follow_mouse = 1,
        sensitivity  = 0,
    },
})

--------------------------------------------------------------------------------
-- LOOK & FEEL  (era conf.d/looknfeel.conf) — perfil meio-termo
--------------------------------------------------------------------------------
hl.config({
    general = {
        gaps_in     = 5,
        gaps_out    = 10,
        border_size = 2,
        col = {
            active_border   = { colors = { "rgba(89b4faee)", "rgba(cba6f7ee)" }, angle = 45 },
            inactive_border = "rgba(313244aa)",
        },
        layout           = "dwindle",
        resize_on_border = true,
        -- CS2 (competitivo, vsync off): permite tear-present -> menor latencia de frame.
        -- Só afeta janelas com a window rule 'immediate' (ver secao WINDOW RULES).
        allow_tearing    = true,
    },

    decoration = {
        rounding = 12,
        active_opacity   = 1.0,
        inactive_opacity = 0.94,     -- janela sem foco levemente apagada
        dim_inactive     = true,
        dim_strength     = 0.08,     -- escurece o resto da tela de leve (visual "app em foco")
        blur = {
            enabled       = true,
            size          = 4,
            passes        = 2,
            ignore_opacity = true,
            popups        = true,
            special       = false,
            xray          = false,
        },
        shadow = {
            enabled      = true,
            range        = 24,
            render_power = 3,
            color        = 0x66000000,
        },
    },

    dwindle = {
        preserve_split = true,
    },

    -- Hyprland 0.56: 'misc:vfr' e 'dwindle:pseudotile' foram removidos; VFR é sempre
    -- ligado agora, e o explicit sync do NVIDIA é automático. Não readicionar.
    misc = {
        vrr                      = 0,
        disable_hyprland_logo    = true,
        disable_splash_rendering = true,
        force_default_wallpaper  = 0,
    },

    cursor = {
        no_hardware_cursors = false, -- toggle de emergência p/ NVIDIA (design §19)
    },

    -- 2 = scanout direto pra tela quando há uma única janela fullscreen sem overlays
    -- (permite tearing). Tira o compositor do caminho no jogo: -latência, +alguns %% FPS.
    -- Antes: bloqueado por "user settings" (opção estava em 0).
    render = {
        direct_scanout = 2,
    },
})

-- Animações estilo grootshell: saída suave, workspace/layers deslizando na horizontal.
hl.curve("smooth", { type = "bezier", points = { { 0.16, 1 }, { 0.3, 1 } } })
hl.curve("snappy", { type = "bezier", points = { { 0.2, 1 }, { 0.2, 1 } } })  -- mantido p/ referência

hl.config({ animations = { enabled = true } })
hl.animation({ leaf = "windows",          enabled = true, speed = 4, bezier = "smooth", style = "popin 80%" })
hl.animation({ leaf = "windowsOut",       enabled = true, speed = 4, bezier = "smooth", style = "popin 80%" })
hl.animation({ leaf = "windowsMove",      enabled = true, speed = 4, bezier = "smooth" })
hl.animation({ leaf = "border",           enabled = true, speed = 6, bezier = "default" })
hl.animation({ leaf = "fade",             enabled = true, speed = 4, bezier = "smooth" })
hl.animation({ leaf = "workspaces",       enabled = true, speed = 5, bezier = "smooth", style = "slide" })
hl.animation({ leaf = "specialWorkspace", enabled = true, speed = 5, bezier = "smooth", style = "slidevert" })
hl.animation({ leaf = "layers",           enabled = true, speed = 4, bezier = "smooth", style = "slide" })

--------------------------------------------------------------------------------
-- WINDOW RULES  (era conf.d/rules.conf) — o motivo da migração
--------------------------------------------------------------------------------
hl.window_rule({ name = "float-pavucontrol",
    match = { class = "^(pavucontrol)$" }, float = true, center = true })
hl.window_rule({ name = "float-blueman",
    match = { class = "^(blueman-manager)$" }, float = true, center = true })
hl.window_rule({ name = "float-nm-connection-editor",
    match = { class = "^(nm-connection-editor)$" }, float = true, center = true })
hl.window_rule({ name = "float-polkit-kde",
    match = { class = "^(org.kde.polkit-kde-authentication-agent-1)$" }, float = true, center = true })
hl.window_rule({ name = "float-spectacle",
    match = { class = "^(org.kde.spectacle)$" }, float = true })
hl.window_rule({ name = "float-portal-filepicker",
    match = { class = "^(xdg-desktop-portal-gtk)$" }, float = true, center = true, size = { 900, 600 } })
hl.window_rule({ name = "float-file-dialogs",
    match = { title = "^(Open File|Save File|Save As).*$" }, float = true })
hl.window_rule({ name = "idleinhibit-fullscreen",
    match = { class = ".*" }, idle_inhibit = "fullscreen" })
-- CS2: tear-present (precisa de general:allow_tearing = true). Menor latência de frame
-- num shooter competitivo com vsync desligado. Sem efeito em qualquer outra janela.
hl.window_rule({ name = "cs2-immediate",
    match = { class = "^(cs2)$" }, immediate = true })

--------------------------------------------------------------------------------
-- LAYER RULES — blur nas surfaces do grootshell
--------------------------------------------------------------------------------
-- Namespaces (ver shell.qml / modules/): grootshell-background (wallpaper, sem
-- blur), grootshell-bar (a barra), grootshell (overlay = borda + painéis).
hl.layer_rule({ name = "grootshell-blur",
    match = { namespace = "^grootshell(-bar)?$" }, blur = true, ignore_alpha = 0.1 })

--------------------------------------------------------------------------------
-- KEYBINDS  (era conf.d/binds.conf) — esquema para teclado 60%
--------------------------------------------------------------------------------

-- ---- Apps & essenciais ----
hl.bind(mod .. " + Return", hl.dsp.exec_cmd("kitty"))
hl.bind(mod .. " + R",      hl.dsp.exec_cmd("grootshell-ipc call launcher toggle"))
hl.bind(mod .. " + E",      hl.dsp.exec_cmd("dolphin"))
hl.bind(mod .. " + B",      hl.dsp.exec_cmd("zen"))
hl.bind(mod .. " + Q",      hl.dsp.window.close())
hl.bind(mod .. " + V",      hl.dsp.exec_cmd("cliphist list | rofi -dmenu | cliphist decode | wl-copy"))  -- fallback sem shell
hl.bind(mod .. " + slash",  hl.dsp.exec_cmd("grootshell-ipc call keybinds toggle"))

-- ---- Foco / movimento ----
hl.bind(mod .. " + H", hl.dsp.focus({ direction = "left" }))
hl.bind(mod .. " + J", hl.dsp.focus({ direction = "down" }))
hl.bind(mod .. " + K", hl.dsp.focus({ direction = "up" }))
hl.bind(mod .. " + L", hl.dsp.focus({ direction = "right" }))
hl.bind(mod .. " + SHIFT + H", hl.dsp.window.move({ direction = "left" }))
hl.bind(mod .. " + SHIFT + J", hl.dsp.window.move({ direction = "down" }))
hl.bind(mod .. " + SHIFT + K", hl.dsp.window.move({ direction = "up" }))
hl.bind(mod .. " + SHIFT + L", hl.dsp.window.move({ direction = "right" }))
hl.bind(mod .. " + space", hl.dsp.window.float({ action = "toggle" }))
hl.bind(mod .. " + F",     hl.dsp.window.fullscreen({ action = "toggle", mode = "fullscreen" }))
hl.bind(mod .. " + T",     hl.dsp.layout("togglesplit"))          -- dwindle
hl.bind(mod .. " + G",     hl.dsp.group.toggle())
hl.bind(mod .. " + SHIFT + Tab", hl.dsp.group.next())             -- ciclar janelas do grupo

-- ---- grootshell (shell Quickshell via IPC) ----
hl.bind(mod .. " + Tab",       hl.dsp.exec_cmd("grootshell-ipc call desktops next"))       -- switcher c/ preview
hl.bind(mod .. " + D",         hl.dsp.exec_cmd("grootshell-ipc call island toggle"))       -- dashboard
hl.bind(mod .. " + N",         hl.dsp.exec_cmd("grootshell-ipc call notifications toggle"))
hl.bind(mod .. " + W",         hl.dsp.exec_cmd("grootshell-ipc call wallpaper toggle"))    -- seletor de wallpaper
hl.bind(mod .. " + C",         hl.dsp.exec_cmd("grootshell-ipc call settings toggle"))
hl.bind(mod .. " + M",         hl.dsp.exec_cmd("grootshell-ipc call island tab media"))
hl.bind(mod .. " + SHIFT + V", hl.dsp.exec_cmd("grootshell-ipc call clipboard toggle"))

-- ---- Mouse ----
hl.bind(mod .. " + mouse:272", hl.dsp.window.drag(),   { mouse = true })
hl.bind(mod .. " + mouse:273", hl.dsp.window.resize(), { mouse = true })
-- Scroll com o mod troca de workspace (só entre as que já existem)
hl.bind(mod .. " + mouse_down", hl.dsp.focus({ workspace = "e+1" }))
hl.bind(mod .. " + mouse_up",   hl.dsp.focus({ workspace = "e-1" }))

-- ---- Submap: resize (entra com SUPER + S) ----
hl.bind(mod .. " + S", hl.dsp.submap("resize"))
hl.define_submap("resize", function()
    hl.bind("H", hl.dsp.window.resize({ x = -40, y =   0, relative = true }), { repeating = true })
    hl.bind("L", hl.dsp.window.resize({ x =  40, y =   0, relative = true }), { repeating = true })
    hl.bind("K", hl.dsp.window.resize({ x =   0, y = -40, relative = true }), { repeating = true })
    hl.bind("J", hl.dsp.window.resize({ x =   0, y =  40, relative = true }), { repeating = true })
    hl.bind("SHIFT + H", hl.dsp.window.resize({ x = -100, y =    0, relative = true }), { repeating = true })
    hl.bind("SHIFT + L", hl.dsp.window.resize({ x =  100, y =    0, relative = true }), { repeating = true })
    hl.bind("SHIFT + K", hl.dsp.window.resize({ x =    0, y = -100, relative = true }), { repeating = true })
    hl.bind("SHIFT + J", hl.dsp.window.resize({ x =    0, y =  100, relative = true }), { repeating = true })
    hl.bind("escape", hl.dsp.submap("reset"))
    hl.bind("Return", hl.dsp.submap("reset"))
end)

-- ---- Workspaces ----
for i = 1, 10 do
    local key = i % 10 -- 10 -> tecla 0
    hl.bind(mod .. " + " .. key,         hl.dsp.focus({ workspace = i }))
    hl.bind(mod .. " + SHIFT + " .. key, hl.dsp.window.move({ workspace = i, follow = true }))
end
hl.bind(mod .. " + minus",         hl.dsp.workspace.toggle_special("magic"))
hl.bind(mod .. " + SHIFT + minus", hl.dsp.window.move({ workspace = "special:magic" }))
hl.bind(mod .. " + comma",          hl.dsp.focus({ monitor = "-1" }))
hl.bind(mod .. " + period",         hl.dsp.focus({ monitor = "+1" }))
hl.bind(mod .. " + SHIFT + comma",  hl.dsp.window.move({ monitor = "-1" }))
hl.bind(mod .. " + SHIFT + period", hl.dsp.window.move({ monitor = "+1" }))

-- ---- Submap: options (entra com SUPER + O) ----
hl.bind(mod .. " + O", hl.dsp.submap("options"))
hl.define_submap("options", function()
    hl.bind("L", function()
        hl.dispatch(hl.dsp.exec_cmd("hyprlock"))
        hl.dispatch(hl.dsp.submap("reset"))
    end)
    hl.bind("E", function()
        hl.dispatch(hl.dsp.exec_cmd(os.getenv("HOME") .. "/.config/rofi/powermenu.sh"))
        hl.dispatch(hl.dsp.submap("reset"))
    end)
    hl.bind("R", function()
        hl.dispatch(hl.dsp.reload_config())
        hl.dispatch(hl.dsp.submap("reset"))
    end)
    hl.bind("W", function()
        hl.dispatch(hl.dsp.exec_cmd("hyprctl hyprpaper reload"))
        hl.dispatch(hl.dsp.submap("reset"))
    end)
    hl.bind("T", function()
        hl.dispatch(hl.dsp.exec_cmd("grootshell-ipc call theme regenerate"))  -- re-roda matugen
        hl.dispatch(hl.dsp.submap("reset"))
    end)
    hl.bind("N", function()
        hl.dispatch(hl.dsp.exec_cmd("grootshell-ipc call notifications clear"))  -- limpa todas
        hl.dispatch(hl.dsp.submap("reset"))
    end)
    hl.bind("escape", hl.dsp.submap("reset"))
end)

-- ---- Sair da sessão (kill switch) ----
hl.bind(mod .. " + SHIFT + Q", hl.dsp.exec_cmd("uwsm stop"))

-- ---- Screenshot (Spectacle) ----
hl.bind(mod .. " + P",         hl.dsp.exec_cmd("spectacle --region --background --nonotify"))
hl.bind(mod .. " + SHIFT + P", hl.dsp.exec_cmd("spectacle --fullscreen --background --nonotify"))
hl.bind(mod .. " + CTRL + P",  hl.dsp.exec_cmd("spectacle --activewindow --background --nonotify"))

-- ---- Mídia / volume ----
hl.bind("XF86AudioRaiseVolume", hl.dsp.exec_cmd("wpctl set-volume -l 1.4 @DEFAULT_AUDIO_SINK@ 5%+"), { locked = true })
hl.bind("XF86AudioLowerVolume", hl.dsp.exec_cmd("wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"),        { locked = true })
hl.bind("XF86AudioMute",        hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"),       { locked = true })
hl.bind("XF86AudioPlay",        hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })
hl.bind("XF86AudioNext",        hl.dsp.exec_cmd("playerctl next"),       { locked = true })
hl.bind("XF86AudioPrev",        hl.dsp.exec_cmd("playerctl previous"),   { locked = true })
hl.bind(mod .. " + bracketright", hl.dsp.exec_cmd("wpctl set-volume -l 1.4 @DEFAULT_AUDIO_SINK@ 5%+"))
hl.bind(mod .. " + bracketleft",  hl.dsp.exec_cmd("wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"))
hl.bind(mod .. " + backslash",    hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"))

--------------------------------------------------------------------------------
-- AUTOSTART  (era conf.d/autostart.conf)
--------------------------------------------------------------------------------
hl.on("hyprland.start", function()
    -- Barra + notificações: grootshell (Quickshell). grootshell tem daemon de
    -- notificação próprio, então o mako sai (só um pode registrar o bus).
    -- Fallback: descomente waybar + mako, comente a linha do qs.
    -- hl.exec_cmd("uwsm app -- waybar")
    -- hl.exec_cmd("uwsm app -- mako")
    hl.exec_cmd("uwsm app -- qs -p " .. os.getenv("HOME") .. "/.config/quickshell/grootshell")
    hl.exec_cmd("uwsm app -- hyprpaper")
    hl.exec_cmd("uwsm app -- hypridle")
    hl.exec_cmd("systemctl --user start hyprpolkitagent")
    hl.exec_cmd("wl-paste --type text  --watch cliphist store")
    hl.exec_cmd("wl-paste --type image --watch cliphist store")
    hl.exec_cmd("uwsm app -- nm-applet --indicator")
    hl.exec_cmd("uwsm app -- blueman-applet")
    hl.exec_cmd("uwsm app -- /usr/bin/kdeconnectd")
    hl.exec_cmd("uwsm app -- kdeconnect-indicator")
end)
