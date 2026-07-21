type CatMascotProps = {
  name: string;
  src: string;
  variant: "naengi" | "koongi";
};

export function CatMascot({ name, src, variant }: CatMascotProps) {
  return (
    <div
      className={`cat-mascot cat-mascot--${variant}`}
      aria-hidden="true"
      data-cat-name={name}
    >
      <div className="cat-mascot__direction">
        <div className="cat-mascot__viewport">
          <img
            className="cat-mascot__sheet"
            src={src}
            alt=""
            decoding="async"
            draggable={false}
          />
        </div>
      </div>
    </div>
  );
}
