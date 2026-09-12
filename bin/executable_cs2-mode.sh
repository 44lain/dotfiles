#!/usr/bin/env bash
# cs2-mode.sh — libera CPU/RAM antes de jogar CS2 e restaura depois.
# Maquina CPU-bound (i3-6300, 2c/4t): processos de fundo derrubam o 1% low.
# NAO toca em armazenamento/Btrfs. Tudo reversivel.
#
# Uso:
#   cs2-mode.sh on    # entra em modo jogo (para Docker, fecha apps pesados)
#   cs2-mode.sh off   # restaura (reinicia Docker)
#   cs2-mode.sh status

set -u

# Apps pesados (flatpak app-ids) fechados no modo jogo:
FLATPAK_APPS=(
  app.zen_browser.zen        # Zen browser
  com.spotify.Client         # Spotify
  dev.vencord.Vesktop        # Discord (Vesktop)
  com.getpostman.Postman     # Postman
  org.pgadmin.pgadmin4       # pgAdmin
)

mem_free() { free -h | awk '/^Mem:/{print "RAM livre: "$7" / "$2}'; }

cmd_on() {
  echo "==> CS2 mode ON"
  mem_free

  if systemctl is-active --quiet docker.service 2>/dev/null; then
    echo "-> parando Docker (libera CPU/RAM)..."
    sudo systemctl stop docker.socket docker.service 2>/dev/null && echo "   Docker parado."
  else
    echo "-> Docker ja estava parado."
  fi

  for app in "${FLATPAK_APPS[@]}"; do
    if flatpak ps --columns=application 2>/dev/null | grep -qx "$app"; then
      echo "-> fechando $app"
      flatpak kill "$app" 2>/dev/null
    fi
  done

  # libera page cache (reduz pressao antes de carregar o jogo do HD)
  echo "-> liberando caches..."
  sync && echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null && echo "   caches liberados."

  # GPU: trava clocks altos p/ nao cair quando o uso fica baixo (CPU-bound) -> evita micro-stutter
  echo "-> fixando clocks da GPU (persistence + lock 1800-2100 MHz)..."
  sudo nvidia-smi -pm 1 >/dev/null 2>&1 && echo "   persistence on."
  sudo nvidia-smi --lock-gpu-clocks=1800,2100 >/dev/null 2>&1 \
    && echo "   GPU travada em 1800-2100 MHz." \
    || echo "   (lock de GPU nao aplicado — segue em auto-boost)"

  echo "Pronto. " ; mem_free
  echo "Dica: abra o CS2 agora. Use 'cs2-mode.sh off' ao terminar."
}

cmd_off() {
  echo "==> CS2 mode OFF (restaurando)"
  if ! systemctl is-active --quiet docker.service 2>/dev/null; then
    echo "-> reiniciando Docker..."
    sudo systemctl start docker.service 2>/dev/null && echo "   Docker ativo."
  else
    echo "-> Docker ja esta ativo."
  fi
  # GPU: libera o lock de clocks (volta ao auto-boost normal)
  echo "-> liberando lock de clocks da GPU..."
  sudo nvidia-smi --reset-gpu-clocks >/dev/null 2>&1 && echo "   clocks da GPU em auto."

  echo "Apps fechados (Zen, Spotify, etc.) reabra manualmente quando quiser."
  mem_free
}

cmd_status() {
  echo "Docker: $(systemctl is-active docker.service 2>/dev/null)"
  echo "Governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)"
  echo "tuned: $(tuned-adm active 2>/dev/null | sed 's/.*: //')"
  mem_free
}

case "${1:-}" in
  on)     cmd_on ;;
  off)    cmd_off ;;
  status) cmd_status ;;
  *) echo "uso: $0 {on|off|status}"; exit 1 ;;
esac
