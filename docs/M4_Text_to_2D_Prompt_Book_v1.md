# M4 — Text-to-2D Prompt Book (v1)

> **Dự án:** AI Asset Studio  
> **Mục tiêu:** So sánh 5 model Text-to-2D bằng **3 nhân vật × 3 bố cục = 9 trường hợp/model**; tối đa **45 ảnh PNG** nếu cả 5 model chạy thành công.  
> **Trạng thái:** Bản prompt dùng để benchmark và học cách viết prompt; có thể chỉnh trước/sau vòng đầu.  
> **Nguồn định hướng:** Ảnh demo 3×3 do ChatGPT tạo và moodboard anime fantasy / modern xianxia mà người dùng đã chọn.

## 1. Phân biệt ba tầng nội dung

- **Character profile (P1, P2, P3):** mô tả *ai/cái gì* được vẽ; tính cách, tóc, mắt, trang phục, màu, phụ kiện. Dùng lại khi đổi bố cục.
- **Style block (S):** mô tả *vẽ theo phong cách gì*; dùng chung cả ba nhân vật để so sánh model công bằng.
- **Composition block (A, B, C):** mô tả *đặt máy ảnh, bố cục và nền ra sao*. Dùng lại khi đổi nhân vật.

Cách ghép nội dung chuẩn:

```text
[CHARACTER PROFILE P1/P2/P3]

[COMPOSITION A/B/C]

[SHARED STYLE S]
```

Với **C — Key Visual**, nối thêm **SCENE C** riêng của từng nhân vật. Mỗi cặp `P×A/B/C` là một positive prompt hoàn chỉnh. Không cần gửi riêng `Character Profile` cho model; runner ghép các phần thành một chuỗi đầu vào và ghi lại chuỗi cuối cùng.

> **Quan trọng:** M4 chỉ nhận **text**. Ảnh demo và moodboard là tài liệu cho người viết/chấm ảnh, **không phải input image** của model. Sinh ba ảnh bằng ba prompt không bảo đảm giữ nguyên 100% khuôn mặt nhân vật.

---

## 2. Style chung — S (English)

```text
Elegant Eastern fantasy anime character illustration, modern xianxia blended with refined contemporary Asian fantasy RPG character design, delicate clean linework, soft painterly shading, luminous expressive eyes, layered flowing fabrics, carefully designed jewelry and ornamental details, graceful stylized proportions, sophisticated costume shapes, muted but luminous colors, thoughtful value contrast, polished professional game concept art, visually coherent design, crisp readable facial features and silhouette.
```

**Giải thích:**
- `Eastern fantasy anime / modern xianxia`: bối cảnh thẩm mỹ.
- `delicate clean linework / soft painterly shading`: nét vẽ và cách đổ bóng.
- `layered flowing fabrics / ornamental details`: mức độ phong phú của trang phục.
- `crisp readable ... silhouette`: quan trọng khi biến concept thành asset 3D sau này.

---

## 3. Ba Character Profile (positive prompt, English)

### P1 — Băng Liên Sư Nữ / Ice Lotus Mage

```text
An adult female ice-lotus mage with a serene, enigmatic presence, long flowing silver-white hair with faint icy-blue undertones, pale blue eyes and a delicate expressive face. She wears a layered white, frost-blue and deep navy Eastern-fantasy robe with translucent flowing sleeve panels, subtle silver embroidery, blue lotus hair ornaments, fine crystal jewelry and slender ribbon tassels. Tiny luminous blue butterflies echo her winter-lotus motif. Her silhouette is elegant, airy and recognizable; the robe layers, ornaments, hands and footwear remain logically designed and visually distinguishable.
```

**Đặc điểm bắt buộc:** tóc trắng bạc dài, mắt xanh băng, hoa sen/bướm xanh, áo trắng–xanh nhiều lớp, khí chất thanh lịch.

### P2 — Hạc Vũ Kiếm Sĩ / Crane-Feather Swordsman

```text
An adult male fantasy swordsman with a reserved, confident presence, tousled silver-ash hair, calm amber-gray eyes and a lean athletic build. He wears an ornate black and charcoal modern-wuxia outfit with deep crimson flowing fabric, subtle antique-gold embroidery, layered tailored sleeves, leather belts, sculpted boots and a refined straight sword. White crane-feather motifs and a few long red ribbons evoke a mystical wandering swordsman. His design balances traditional Eastern martial-arts clothing with modern RPG tailoring; the sword, costume layers and footwear are distinct and functional-looking.
```

**Đặc điểm bắt buộc:** kiếm sĩ nam tóc bạc, đen–đỏ–vàng cổ, kiếm thẳng, họa tiết lông hạc, trang phục võ hiệp pha hiện đại.

### P3 — Mộc Linh Triệu Hồn / Verdant Spirit Summoner

```text
An adult female woodland spirit summoner with soft mint-green hair, luminous green-gold eyes and a gentle, observant expression. She wears an ivory tunic dress under a layered sage-green cloak, dark olive accents, embroidered botanical patterns, delicate jade ornaments, leaf-shaped clasps and small charms. Fine vine-like shapes and flowing fabric give the costume a light magical feeling. A tiny owl-like forest spirit may accompany her as a secondary detail without obscuring the character. Her silhouette is youthful yet refined, clear and distinct from the other two characters.
```

**Đặc điểm bắt buộc:** tóc xanh mint, trang phục xanh lá–kem, họa tiết thực vật, trâm ngọc/bùa chú, cảm giác triệu hồi tự nhiên.

---

## 4. Ba kiểu bố cục — Composition Blocks (English)

### A — Full-body Character Design

**Mục tiêu:** kiểm tra tỷ lệ, đầy đủ cơ thể, trang phục, giày, phụ kiện; ưu tiên cho pipeline Image-to-3D ở M5.

```text
Full-body single-character game design illustration, standing in a relaxed neutral three-quarter-front pose, entire figure visible from the top of the head to the soles of the shoes, both hands and both feet clearly visible, readable costume construction and accessories, balanced centered composition, simple warm off-white studio background, minimal props, no interface labels, no inset portraits, no extra character, no dramatic motion blur.
```

**Tỷ lệ tham khảo:** dọc, khoảng 2:3 hoặc 3:4; runner lưu độ phân giải **thực tế** mà mỗi model dùng.

### B — Portrait / Beauty Close-up

**Mục tiêu:** kiểm tra mặt, mắt, tóc, sắc thái cảm xúc, đường nét và phụ kiện.

```text
Single-character head-and-shoulders portrait, close-up framing with the entire face clearly visible, natural elegant expression, focus on eye detail, hair strands, delicate ornaments and believable facial proportions, soft atmospheric light, restrained background matching the character's palette, clear separation of face and background, refined painterly details, no text or decorative panels.
```

**Tỷ lệ tham khảo:** vuông, 1:1.

### C — Key Visual / Fantasy Illustration

**Mục tiêu:** kiểm tra tính nghệ thuật, ánh sáng, tương tác với bối cảnh và mức độ sinh động.

```text
Premium fantasy RPG key visual illustration of one clearly recognizable main character in an elegant dynamic pose, cinematic lighting, graceful motion of hair and fabric, painterly atmospheric depth, magical effects that complement rather than conceal the face and costume, strong focal hierarchy, an expressive but uncluttered fantasy environment, detailed yet coherent composition, no typography, no watermark, no interface graphics.
```

**Tỷ lệ tham khảo:** ngang 3:2 hoặc dọc 3:4; giữ gần tương đương giữa model trong cùng trường hợp.

**Scene C riêng của từng nhân vật:**

- **P1-C:** `A moonlit winter garden with crystalline lotus blossoms, drifting blue butterflies, delicate frost particles and a cool blue-white glow.`
- **P2-C:** `An ancient shrine walkway under falling crimson maple leaves, a white crane passing overhead, wind-swept ribbons and warm dusk light.`
- **P3-C:** `A quiet enchanted woodland with pale golden light through leaves, floating pollen, soft moss, a glowing grimoire and a small owl spirit nearby.`

---

## 5. Danh sách chính xác 9 trường hợp

| ID | Nhân vật | Bố cục | Ghép prompt |
|---|---|---|---|
| P1-A | Ice Lotus Mage | Full-body | P1 + A + S |
| P1-B | Ice Lotus Mage | Portrait | P1 + B + S |
| P1-C | Ice Lotus Mage | Key Visual | P1 + C + scene P1-C + S |
| P2-A | Crane-Feather Swordsman | Full-body | P2 + A + S |
| P2-B | Crane-Feather Swordsman | Portrait | P2 + B + S |
| P2-C | Crane-Feather Swordsman | Key Visual | P2 + C + scene P2-C + S |
| P3-A | Verdant Spirit Summoner | Full-body | P3 + A + S |
| P3-B | Verdant Spirit Summoner | Portrait | P3 + B + S |
| P3-C | Verdant Spirit Summoner | Key Visual | P3 + C + scene P3-C + S |

## 6. Negative prompt (tùy chọn, KHÔNG phải thành phần bắt buộc)

```text
low quality, low resolution, blurry, extra limbs, extra fingers, missing fingers, malformed hands, deformed face, duplicate character, cropped feet, cropped head, watermark, logo, signature, unintended text, cluttered composition, photorealistic, chibi
```

**Sử dụng:** chỉ áp dụng nếu model/pipeline **thực sự hỗ trợ** negative prompt. Không đưa cùng một negative prompt vào mọi model một cách máy móc; trong báo cáo phải ghi model nào dùng và model nào không. Những từ như `cropped feet` có ý nghĩa nhất với A, không nên mặc định áp dụng cho B là portrait.

## 7. Công bằng và tái lập benchmark

- **Ứng viên:** Animagine XL 4.0, SDXL Base 1.0, FLUX.2 Klein 4B, Z-Image-Turbo, MOSS-Image-SFT.
- **Mỗi model:** một ảnh PNG trên mỗi trường hợp (`P1-A` … `P3-C`), tổng **9 ảnh/model**; 5 model thành công = **45 ảnh**.
- Giữ **ngữ nghĩa nội dung** tương đương giữa các model; có thể chuyển sang **tag prompt** cho Animagine, nhưng lưu cả canonical và prompt thực tế.
- Log **seed, steps, guidance, scheduler, precision, kích thước ảnh, checkpoint/revision, thời gian download, load, inference, peak VRAM GPU0/GPU1, peak host RAM, lỗi**. Seed số giống nhau không bảo đảm ảnh tương đương giữa kiến trúc model khác nhau.
- GPU0 và GPU1 chạy **hai tiến trình/model độc lập** khi được kiểm chứng khả thi; **không** coi 2×T4 là 1 GPU 30 GiB. Nếu không an toàn, chạy tuần tự trong một Kaggle notebook.
- Không fine-tune, không dùng ảnh tham chiếu trong benchmark Text-to-2D, không tự ý thay đổi `CONTRACTS.md v1.0`.
- Người dùng **tự chấm ảnh** trước khi chọn model sản xuất. Không chấm ảnh mô hình chạy lỗi bằng hình dự phòng.

## 8. Rubric chấm ảnh (1–5 điểm / tiêu chí)

| Tiêu chí | Câu hỏi khi chấm |
|---|---|
| Đúng brief | Có đúng tóc, mắt, trang phục, màu và motif không? |
| Thẩm mỹ | Ảnh có đẹp và hợp gu của tôi không? |
| Anatomy | Tay, chân, mắt, cấu trúc cơ thể có hợp lý không? |
| Trang phục & silhouette | Các lớp áo và phụ kiện có rõ, hợp logic không? |
| Hữu dụng cho 3D (A) | Có nhìn rõ toàn thân, giày, tay, cấu trúc trang phục không? |
| Minh họa (B/C) | Khuôn mặt, biểu cảm và bầu không khí có đạt không? |

Đánh giá riêng **chi phí/thời gian**, không cộng lẫn vào điểm thẩm mỹ nếu chưa thống nhất trọng số.

## 9. Học cách viết prompt: công thức thực hành

Một prompt có thể xây từ năm thành phần:

```text
SUBJECT + DISTINCTIVE FEATURES + ART STYLE + COMPOSITION + LIGHTING / BACKGROUND
```

**Ví dụ từ đơn giản đến rõ ràng:**

- **Quá chung:** `a beautiful fantasy mage`
- **Thêm chủ thể:** `an adult female ice mage with long silver hair and pale blue eyes`
- **Thêm thiết kế:** `layered white and navy robes, silver ornaments, ice-lotus hairpin, blue butterflies`
- **Thêm phong cách:** `eastern fantasy anime, modern xianxia, fine linework, soft painterly shading`
- **Thêm bố cục:** `full body, neutral standing pose, hands and shoes visible, clean background`

**Cách tự học hiệu quả:** mỗi lần chỉ thay **một nhóm biến** (chẳng hạn style, composition hoặc trang phục), giữ nguyên các nhóm khác, ghi lại ảnh và sự khác biệt. Khi prompt quá dài mà ảnh vẫn sai, ưu tiên sửa **thông tin cốt lõi ở đầu prompt** thay vì thêm nhiều tính từ vô nghĩa.

### Bài tập nhỏ

Tự viết một nhân vật thứ tư bằng năm dòng: (1) nhân vật/vai trò; (2) tóc & mắt; (3) trang phục; (4) motif & màu; (5) bố cục. Sau đó dùng `S` + `A` và so kết quả với bộ benchmark này.
