import logoImage from "../assets/rubriceye-logo.jpeg";

interface BrandedLoaderProps {
  message?: string;
}

export default function BrandedLoader({ message }: BrandedLoaderProps) {
  return (
    <div className="branded-loader" role="status">
      <img
        src={logoImage}
        alt=""
        className="branded-loader-logo"
        aria-hidden="true"
      />
      {message && <p className="branded-loader-text">{message}</p>}
    </div>
  );
}
