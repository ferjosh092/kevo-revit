# Skills del proyecto

Todas se copiaron sin cambios desde su repositorio público y se revisaron antes de instalar:
son instrucciones en Markdown, sin hooks ni cambios de permisos. Licencia MIT en todas.

| Skill | Origen (commit) | Para qué |
|---|---|---|
| `frontend-design` | [anthropics/skills](https://github.com/anthropics/skills) `dbd4588` | Criterios de diseño visual para páginas y componentes. |
| `webapp-testing` | [anthropics/skills](https://github.com/anthropics/skills) `dbd4588` | Probar la web con Playwright: capturas, consola, interacción. |
| `motion-design` | [lottiefiles/motion-design-skill](https://github.com/lottiefiles/motion-design-skill) `f9a8a04` | Principios de animación: tiempos, curvas, coreografía, principios de Disney aplicados a interfaces. |
| `design-dna` | [zanwei/design-dna](https://github.com/zanwei/design-dna) `593e39b` | Extraer y aplicar la identidad visual (tokens, estilo, efectos) de una referencia. Sus scripts opcionales miden colores de una imagen con `sharp`, en local y sin red. |
| `gsap-core`, `gsap-timeline`, `gsap-scrolltrigger`, `gsap-plugins`, `gsap-performance`, `gsap-utils` | [greensock/gsap-skills](https://github.com/greensock/gsap-skills) `aed9cfd` (oficial de GSAP) | Uso correcto de GSAP, ScrollTrigger, SplitText y rendimiento de animaciones. No se instalaron `gsap-react` ni `gsap-frameworks` porque la web no usa React ni Vue. |
| `ui-ux-pro-max` | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) `7246805` | Base de datos de diseño UI/UX: estilos, paletas por tipo de producto, combinaciones de fuentes, 119 reglas de UX y accesibilidad, presets de GSAP. Sus scripts (solo Python estándar, sin red) buscan en esos CSV; ejecútalos con `python3 .claude/skills/ui-ux-pro-max/scripts/search.py "<consulta>"` (su SKILL.md usa `${CLAUDE_PLUGIN_ROOT}`, pensado para instalarlo como plugin). Solo escribe archivos con `--persist`. |
| `threejs-*` (10 skills) | [CloudAI-X/threejs-skills](https://github.com/CloudAI-X/threejs-skills) `b1c6230` | Escena, geometría, materiales, luces, texturas, shaders, interacción, carga de modelos y postprocesado en Three.js. |

Para actualizar: vuelve a copiar la carpeta desde un commit nuevo y revisa el diff antes de subirlo.
