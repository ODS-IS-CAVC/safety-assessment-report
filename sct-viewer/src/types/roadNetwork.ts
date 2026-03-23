// OpenDRIVE道路ネットワークの型定義

export interface RoadPoint {
  x: number;
  y: number;
  z: number;
  heading: number;
  s: number;
}

export interface LaneData {
  road_id: number;
  lane_id: number;
  points: RoadPoint[];
}

export interface RoadData {
  road_id: number;
  length: number;
  lanes: LaneData[];
}

export interface RoadNetworkData {
  roads: RoadData[];
}
