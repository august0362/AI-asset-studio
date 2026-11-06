import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import { Failure } from "../../components/ui";
import { useI18n } from "../../i18n";
import { Modal } from "./shared";
import { removeLayout } from "./canvasLayout";

export function DeleteCharacterDialog({ character, onClose }: {
  character: { character_id: string; name: string }; onClose: () => void;
}) {
  const { t } = useI18n(), cache = useQueryClient(), navigate = useNavigate();
  const deletion = useMutation({
    mutationFn: () => api.deleteCharacter(character.character_id),
    onSuccess: () => {
      removeLayout(character.character_id);
      cache.removeQueries({ queryKey: ["character", character.character_id] });
      cache.removeQueries({ queryKey: ["character-stage", character.character_id] });
      void cache.invalidateQueries({ queryKey: ["characters"] });
      onClose();
      navigate("/characters");
    },
  });
  return <Modal title={t("char.deleteTitle", { name: character.name })} onClose={() => { if (!deletion.isPending) onClose(); }}>
    <p>{t("char.deleteHelp")}</p>
    {deletion.error && <Failure error={deletion.error} />}
    <div className="character-actions">
      <button autoFocus disabled={deletion.isPending} onClick={onClose}>{t("char.cancel")}</button>
      <button disabled={deletion.isPending} onClick={() => deletion.mutate()}>{t("char.delete")}</button>
    </div>
  </Modal>;
}
