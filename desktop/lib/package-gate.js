export function assertInternalDmg(pkg) {
  const mac = pkg?.build?.mac ?? {};
  const dmg = pkg?.build?.dmg ?? {};
  const contents = dmg.contents ?? [];
  const app = contents.find((item) => item.type === 'file');
  const applications = contents.find((item) => item.type === 'link');
  if (!app || !applications || !(app.x < applications.x)) {
    throw new Error('El icono de Vocify va a la izquierda y Applications a la derecha');
  }
  if (!dmg.background) throw new Error('Falta el fondo del DMG');
  const publishAsSigned = Boolean(mac.identity) && mac.hardenedRuntime === true;
  if (publishAsSigned) {
    throw new Error('No se publica como distribución firmada sin Developer ID confirmado');
  }
  return { publishAsSigned: false, app, applications };
}

export function assertArtifactComplete(relativePaths) {
  const hasHelper = relativePaths.some((file) => file.includes('vocify-tap'));
  const hasShared = relativePaths.some((file) => file.includes('shared/ui/'));
  if (!hasHelper || !hasShared) {
    throw new Error('Artefacto incompleto: faltan el helper vocify-tap o shared/ui');
  }
}
