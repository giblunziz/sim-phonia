/**
 * PhotoMessage — bulle "SMS reçu" affichant une photo générée par photo_service.
 *
 * Propos : afficher une image envoyée via SSE par le bus `photo` quand un
 * LLM-joueur a déclenché `take_shoot` ou `take_selfy`. L'image est servie
 * par simphonia via `GET /photos/{photo_id}` (cf. `api/simphonia.photoUrl`).
 *
 * Props :
 *   - speaker    : nom du personnage qui a pris la photo (ex: "aurore")
 *   - url        : URL servable de l'image (ex: "/photos/<uuid>")
 *   - photoType  : "shoot" | "selfy" — pour le label
 *   - isFrom     : bool, alignement bulle (true = côté envoyeur)
 */
export default function PhotoMessage({ speaker, url, photoType, isFrom }) {
  const kind = photoType === 'selfy' ? 'selfie' : 'photo';
  return (
    <div className={`message message-photo ${isFrom ? 'message-from' : 'message-to'}`}>
      <span className="message-speaker">
        {speaker} · 📷 {kind}
      </span>
      <a href={url} target="_blank" rel="noopener noreferrer" className="photo-link">
        <img src={url} alt={`${kind} de ${speaker}`} className="photo-image" />
      </a>
    </div>
  );
}
